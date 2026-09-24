const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {"content-type": "application/json"},
});

const bearer = request => request.headers.get("authorization") || "";
const controlAuthorized = (request, env) => bearer(request) === `Bearer ${env.CONTROL_PLANE_WRITE_SECRET}`;
const readAuthorized = (request, env) => bearer(request) === `Bearer ${env.RUNTIME_READ_SECRET}`;
const reconciliationUrl = "https://global-hybrid-mcp-v2.onrender.com/internal/vehicle-knowledge/reconcile";
const reconciliationBody = '{"operation":"vehicle-knowledge-reconcile"}';
const rejectInjection = body => [
  "sql", "raw_sql", "table", "table_name", "spreadsheet_id", "verified",
  "promoted", "promotion_state", "authority_state", "query_ready",
].some(key => key in body);

const required = (body, names) => {
  for (const name of names) {
    if (typeof body[name] !== "string" || body[name].trim() === "") {
      throw new Error(`INVALID_${name.toUpperCase()}`);
    }
  }
};

const database = env => {
  if (!env.DB || typeof env.DB.prepare !== "function" || typeof env.DB.batch !== "function") {
    throw new Error("D1_BINDING_REQUIRED");
  }
  return env.DB;
};

const parsePayload = row => row ? JSON.parse(row.payload) : null;

async function control(db, path, body) {
  if (path === "/internal/control/inventory-observation") {
    required(body, ["observation_id", "source_revision", "observed_at"]);
    const rows = Array.isArray(body.rows) ? body.rows : [];
    const statements = [db.prepare(
      "INSERT INTO inventory_source_observation(id,source_revision,payload,observed_at) VALUES(?,?,?,?)",
    ).bind(body.observation_id, body.source_revision, JSON.stringify(body.payload || {}), body.observed_at)];
    for (const row of rows) {
      required(row, ["id"]);
      statements.push(db.prepare(
        "INSERT INTO inventory_vehicle_row(id,observation_id,payload) VALUES(?,?,?)",
      ).bind(row.id, body.observation_id, JSON.stringify(row.payload || {})));
    }
    await db.batch(statements);
    return {state: "RECORDED", observation_id: body.observation_id, row_count: rows.length};
  }
  if (path === "/internal/control/coverage-work") {
    required(body, ["work_id", "scope_key"]);
    await db.prepare(
      "INSERT INTO vehicle_coverage_work(id,scope_key,state) VALUES(?,?,?)",
    ).bind(body.work_id, body.scope_key, "OPEN").run();
    return {state: "OPEN", work_id: body.work_id};
  }
  if (path === "/internal/control/verified-revision") {
    required(body, ["work_id", "revision_id", "receipt_id"]);
    if (!body.receipt || body.receipt.decision !== "PASS" || !Array.isArray(body.facts)) {
      throw new Error("VERIFIED_RECEIPT_REQUIRED");
    }
    const work = await db.prepare(
      "SELECT state FROM vehicle_coverage_work WHERE id=?",
    ).bind(body.work_id).first();
    if (!work || work.state !== "OPEN") throw new Error("COVERAGE_WORK_NOT_OPEN");
    const statements = [
      db.prepare(
        "INSERT INTO vehicle_fact_verification_receipt(id,work_id,decision,payload) VALUES(?,?,?,?)",
      ).bind(body.receipt_id, body.work_id, "PASS", JSON.stringify(body.receipt)),
      db.prepare(
        "INSERT INTO vehicle_configuration_revision(id,work_id,state,payload) VALUES(?,?,?,?)",
      ).bind(body.revision_id, body.work_id, "VERIFIED", JSON.stringify(body.revision || {})),
    ];
    for (const fact of body.facts) {
      required(fact, ["fact_id"]);
      statements.push(db.prepare(
        "INSERT INTO vehicle_configuration_fact(id,revision_id,payload) VALUES(?,?,?)",
      ).bind(fact.fact_id, body.revision_id, JSON.stringify(fact.payload || {})));
    }
    statements.push(db.prepare(
      "UPDATE vehicle_coverage_work SET state='VERIFIED' WHERE id=? AND state='OPEN'",
    ).bind(body.work_id));
    await db.batch(statements);
    return {state: "VERIFIED", revision_id: body.revision_id};
  }
  if (path === "/internal/control/snapshot-promote") {
    required(body, ["snapshot_id", "promotion_id", "promoted_at"]);
    const build = await db.prepare(
      "SELECT id FROM vehicle_snapshot_build WHERE id=?",
    ).bind(body.snapshot_id).first();
    if (!build) throw new Error("SNAPSHOT_CANDIDATE_MISSING");
    await db.batch([
      db.prepare(
        "INSERT INTO vehicle_snapshot_promotion(id,snapshot_id,promoted_at) VALUES(?,?,?)",
      ).bind(body.promotion_id, body.snapshot_id, body.promoted_at),
      db.prepare(
        "INSERT INTO vehicle_snapshot_active(singleton,snapshot_id,promotion_id) VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET snapshot_id=excluded.snapshot_id,promotion_id=excluded.promotion_id",
      ).bind(body.snapshot_id, body.promotion_id),
    ]);
    return {state: "PROMOTED", snapshot_id: body.snapshot_id};
  }
  throw new Error("UNSUPPORTED_CONTROL_PATH");
}

async function activeSnapshot(db) {
  return db.prepare(
    "SELECT a.snapshot_id,a.promotion_id,b.builder_version,b.payload FROM vehicle_snapshot_active a JOIN vehicle_snapshot_build b ON b.id=a.snapshot_id WHERE a.singleton=1",
  ).first();
}

async function read(db, path, params) {
  const active = await activeSnapshot(db);
  if (!active) return {state: "PROVIDER_UNAVAILABLE", provider_id: "cloudflare-d1-http", provider_version: "unresolved"};
  const snapshot = parsePayload(active);
  if (path === "/v1/vehicle-config/readback") {
    return {
      provider_id: "cloudflare-d1-http",
      provider_version: active.snapshot_id,
      snapshot_id: active.snapshot_id,
      source_revision: snapshot.source_revision || null,
      generated_at: snapshot.generated_at || null,
      active: true,
      readback_at: new Date().toISOString(),
    };
  }
  const query = {
    market: params.market,
    model_year: Number(params.model_year),
    make: params.make,
    model: params.model,
  };
  const configurations = (snapshot.configurations || []).filter(item =>
    item.market === query.market && Number(item.model_year) === query.model_year &&
    item.make === query.make && item.model === query.model
  );
  return {
    state: configurations.length ? "HIT" : "MISS",
    query,
    configurations,
    uncertainties: [],
    provenance: [`snapshot:${active.snapshot_id}`],
    provider_id: "cloudflare-d1-http",
    provider_version: active.snapshot_id,
  };
}

export async function handleRequest(request, env) {
  const url = new URL(request.url);
  const controlPaths = new Set([
    "/internal/control/inventory-observation",
    "/internal/control/coverage-work",
    "/internal/control/verified-revision",
    "/internal/control/snapshot-promote",
  ]);
  try {
    if (controlPaths.has(url.pathname)) {
      if (!controlAuthorized(request, env)) return json({error: "CONTROL_AUTH_REQUIRED"}, 403);
      const body = await request.json();
      if (rejectInjection(body)) return json({error: "DIRECT_AUTHORITY_INJECTION"}, 400);
      return json(await control(database(env), url.pathname, body));
    }
    if (url.pathname === "/v1/vehicle-config/query" || url.pathname === "/v1/vehicle-config/readback") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      return json(await read(database(env), url.pathname, Object.fromEntries(url.searchParams)));
    }
    return json({error: "NOT_FOUND"}, 404);
  } catch (error) {
    return json({state: "HOLD", blocker: error.message || "D1_UNAVAILABLE"}, 503);
  }
}

export async function handleScheduled(_event, env, _ctx, fetcher = fetch) {
  if (!env.RENDER_RECONCILIATION_SHARED_SECRET) throw new Error("RECONCILIATION_SECRET_REQUIRED");
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.RENDER_RECONCILIATION_SHARED_SECRET),
    {name: "HMAC", hash: "SHA-256"},
    false,
    ["sign"],
  );
  const signatureBytes = await crypto.subtle.sign(
    "HMAC", key, new TextEncoder().encode(reconciliationBody),
  );
  const signature = [...new Uint8Array(signatureBytes)]
    .map(value => value.toString(16).padStart(2, "0")).join("");
  const response = await fetcher(reconciliationUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-vehicle-control-signature": signature,
    },
    body: reconciliationBody,
  });
  if (!response.ok) throw new Error("RENDER_RECONCILIATION_FAILED");
}

export default {fetch: handleRequest, scheduled: handleScheduled};
