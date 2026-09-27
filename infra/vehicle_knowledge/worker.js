const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {"content-type": "application/json"},
});

const bearer = request => request.headers.get("authorization") || "";
const controlAuthorized = (request, env) => bearer(request) === `Bearer ${env.CONTROL_PLANE_WRITE_SECRET}`;
const readAuthorized = (request, env) => bearer(request) === `Bearer ${env.RUNTIME_READ_SECRET}`;
const reconciliationUrl = "https://global-hybrid-mcp-v2.onrender.com/internal/vehicle-knowledge/reconcile";
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

const canonicalJson = value => {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
};

const collision = () => { throw new Error("IDENTITY_COLLISION"); };

const database = env => {
  if (!env.DB || typeof env.DB.prepare !== "function" || typeof env.DB.batch !== "function") {
    throw new Error("D1_BINDING_REQUIRED");
  }
  return env.DB;
};
const mediaBucket = env => {
  if (!env.MEDIA_BUCKET || typeof env.MEDIA_BUCKET.get !== "function" ||
      typeof env.MEDIA_BUCKET.put !== "function" ||
      typeof env.MEDIA_BUCKET.delete !== "function") throw new Error("MEDIA_OBJECT_STORE_REQUIRED");
  return env.MEDIA_BUCKET;
};

const parsePayload = row => row ? JSON.parse(row.payload) : null;

const sha256Hex = async value => {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(bytes)].map(item => item.toString(16).padStart(2, "0")).join("");
};

async function control(db, path, body, env) {
  if (path === "/internal/control/media-object-probe") {
    required(body, ["raw_base64", "expected_sha256", "expected_object_key",
      "deployment_id", "nonce"]);
    if (!/^[A-Za-z0-9_-]{8,64}$/.test(body.deployment_id) ||
        !/^[0-9a-f]{32}$/.test(body.nonce)) throw new Error("MEDIA_PROBE_SCOPE_INVALID");
    const raw = Uint8Array.from(atob(body.raw_base64), char => char.charCodeAt(0));
    const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", raw))]
      .map(item => item.toString(16).padStart(2, "0")).join("");
    const key = `__probe__/rd021/${body.deployment_id}/${body.nonce}`;
    if (!raw.length || digest !== body.expected_sha256 || key !== body.expected_object_key)
      throw new Error("MEDIA_PROBE_OBJECT_IDENTITY_MISMATCH");
    const bucket = mediaBucket(env);
    const existing = await bucket.get(key);
    if (existing) throw new Error("MEDIA_PROBE_NONCE_REUSED");
    await bucket.put(key, raw);
    let verified = false;
    try {
      const readback = await bucket.get(key);
      if (!readback) throw new Error("MEDIA_PROBE_OBJECT_MISSING");
      const found = new Uint8Array(await readback.arrayBuffer());
      const foundHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", found))]
        .map(item => item.toString(16).padStart(2, "0")).join("");
      verified = foundHash === digest && found.byteLength === raw.byteLength &&
        !found.some((value, index) => value !== raw[index]);
    } finally {
      try {
        await bucket.delete(key);
        if (await bucket.get(key)) throw new Error("HOLD_PROBE_CLEANUP_FAILED");
      } catch (_) { throw new Error("HOLD_PROBE_CLEANUP_FAILED"); }
    }
    if (!verified) throw new Error("MEDIA_PROBE_OBJECT_READBACK_MISMATCH");
    const cleanupDigest = await sha256Hex(`${key}:NOT_FOUND`);
    return {state: "PROBE_PASS", object_key: key, raw_sha256: digest,
      object_size: raw.byteLength, cleanup_state: "NOT_FOUND",
      cleanup_readback_digest: cleanupDigest};
  }
  if (path === "/internal/control/creative-media-ref") {
    required(body, ["creative_ref_id", "media_asset_id", "vehicle_instance_id", "target_column"]);
    if (body.target_column !== "\u92b7\u552e\u7d20\u6750Refs" || !Array.isArray(body.channels) ||
        body.channels.length === 0 || body.channels.some(channel =>
          !["8891", "FB", "Marketplace", "IG"].includes(channel)))
      throw new Error("CREATIVE_REF_SCOPE_INVALID");
    const expected = `creative:${await sha256Hex(`${body.vehicle_instance_id}\0${body.media_asset_id}`)}`;
    if (body.creative_ref_id !== expected) throw new Error("CREATIVE_REF_ID_INVALID");
    const asset = await db.prepare(
      "SELECT truth_eligibility,source_lineage FROM media_asset WHERE media_asset_id=?",
    ).bind(body.media_asset_id).first();
    if (!asset || asset.truth_eligibility !== "FORBIDDEN" ||
        asset.source_lineage !== body.vehicle_instance_id)
      throw new Error("CREATIVE_TRUTH_LINEAGE_REQUIRED");
    const existing = await db.prepare(
      "SELECT * FROM creative_media_ref WHERE creative_ref_id=?",
    ).bind(body.creative_ref_id).first();
    if (existing) return {state: "IDEMPOTENT_SUCCESS", creative_ref_id: existing.creative_ref_id};
    const channels = JSON.stringify([...new Set(body.channels)].sort());
    await db.prepare(
      "INSERT INTO creative_media_ref(creative_ref_id,media_asset_id,vehicle_instance_id,target_column,channels_json,admitted_at) VALUES(?,?,?,?,?,?)",
    ).bind(body.creative_ref_id,body.media_asset_id,body.vehicle_instance_id,
      body.target_column,channels,new Date().toISOString()).run();
    return {state: "RECORDED", creative_ref_id: body.creative_ref_id};
  }
  if (path === "/internal/control/media-asset") {
    required(body, ["media_asset_id", "raw_sha256", "normalized_pixel_hash", "perceptual_fingerprint",
      "object_key", "mime", "provenance_class", "provenance_confidence", "earlier_source_status",
      "producing_activity", "truth_eligibility", "first_seen_at",
      "source_lineage", "task_lineage", "raw_base64"]);
    if (!/^media:[0-9a-f]{64}$/.test(body.media_asset_id) ||
        body.media_asset_id !== `media:${body.raw_sha256}`) throw new Error("MEDIA_ID_INVALID");
    if (!Number.isInteger(body.width) || body.width < 1 ||
        !Number.isInteger(body.height) || body.height < 1) throw new Error("MEDIA_DIMENSIONS_INVALID");
    const raw = Uint8Array.from(atob(body.raw_base64), char => char.charCodeAt(0));
    const rawHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", raw))]
      .map(item => item.toString(16).padStart(2, "0")).join("");
    if (rawHash !== body.raw_sha256) throw new Error("MEDIA_RAW_HASH_MISMATCH");
    if (body.object_key !== `media/sha256/${rawHash}` ||
        body.object_size !== raw.byteLength) throw new Error("MEDIA_OBJECT_IDENTITY_MISMATCH");
    const existing = await db.prepare("SELECT media_asset_id,source_lineage FROM media_asset WHERE raw_sha256=?")
      .bind(body.raw_sha256).first();
    if (existing) {
      if (existing.source_lineage !== body.source_lineage) throw new Error("MEDIA_SOURCE_LINEAGE_CONFLICT");
      return {state: "EXACT_DUPLICATE", media_asset_id: existing.media_asset_id};
    }
    const parentId = body.parent_asset_id || null;
    if (parentId === body.media_asset_id) throw new Error("MEDIA_LINEAGE_CYCLE");
    const parent = parentId ? await db.prepare(
      "SELECT source_lineage,truth_eligibility,provenance_confidence,independent_evidence_id FROM media_asset WHERE media_asset_id=?",
    ).bind(parentId).first() : null;
    if (parentId && !parent) throw new Error("MEDIA_PARENT_MISSING");
    if (parent && parent.source_lineage !== body.source_lineage) throw new Error("MEDIA_PARENT_SCOPE_MISMATCH");
    if (parent && parent.truth_eligibility === "FORBIDDEN" &&
        body.truth_eligibility !== "FORBIDDEN") throw new Error("MEDIA_FORBIDDEN_LINEAGE_UPGRADE");
    const rank = {FORBIDDEN: 0, TRUTH_UNRESOLVED: 1, LIMITED: 2, FIELD_SCOPED: 3, FULL: 4};
    if (parent && rank[body.truth_eligibility] > rank[parent.truth_eligibility])
      throw new Error("MEDIA_LINEAGE_TRUTH_UPGRADE");
    const confidenceRank = {UNKNOWN: 0, PARTIAL: 1, VERIFIED: 2};
    if (parent && confidenceRank[body.provenance_confidence] >
        confidenceRank[parent.provenance_confidence]) throw new Error("MEDIA_LINEAGE_PROVENANCE_UPGRADE");
    if (parent && body.independent_evidence_id !== parent.independent_evidence_id)
      throw new Error("MEDIA_INDEPENDENT_EVIDENCE_ESCALATION");
    if (body.provenance_class === "ORIGINAL_EVIDENCE" &&
        (parent || body.producing_activity !== "ORIGINAL_CAPTURE" ||
         body.truth_eligibility !== "FULL" || body.provenance_confidence !== "VERIFIED" ||
         body.independent_evidence_id !== body.media_asset_id))
      throw new Error("MEDIA_ORIGINAL_UPGRADE_FORBIDDEN");
    if (body.provenance_class === "FIRST_OBSERVED_EXTERNAL" &&
        (parent || body.producing_activity !== "FIRST_OBSERVED_EXTERNAL" ||
         !["FIELD_SCOPED", "LIMITED"].includes(body.truth_eligibility) ||
         body.provenance_confidence === "VERIFIED"))
      throw new Error("MEDIA_FIRST_OBSERVED_ESCALATION");
    if (["AI_EDITED", "AI_GENERATED", "COMPOSITED"].includes(body.provenance_class) &&
        body.truth_eligibility !== "FORBIDDEN") throw new Error("MEDIA_CREATIVE_TRUTH_FORBIDDEN");
    if (body.provenance_class === "PROVENANCE_UNVERIFIED" &&
        !(body.truth_eligibility === "LIMITED" && body.provenance_confidence === "UNKNOWN") &&
        !(parent?.truth_eligibility === "FORBIDDEN" && body.truth_eligibility === "FORBIDDEN"))
      throw new Error("MEDIA_UNVERIFIED_SCOPE_INVALID");
    if (body.provenance_class === "SIMILARITY_UNRESOLVED" &&
        ["FULL", "FIELD_SCOPED", "LIMITED"].includes(body.truth_eligibility))
      throw new Error("MEDIA_UNRESOLVED_TRUTH_FORBIDDEN");
    const bucket = mediaBucket(env);
    const previous = await bucket.get(body.object_key);
    if (previous) {
      const stored = new Uint8Array(await previous.arrayBuffer());
      const storedHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", stored))]
        .map(item => item.toString(16).padStart(2, "0")).join("");
      if (storedHash !== rawHash) throw new Error("MEDIA_OBJECT_HASH_MISMATCH");
    } else {
      await bucket.put(body.object_key, raw);
    }
    try {
      await db.prepare(
        "INSERT INTO media_asset(media_asset_id,raw_sha256,object_key,object_size,normalized_pixel_hash,perceptual_fingerprint,width,height,mime,provenance_class,provenance_confidence,earlier_source_status,parent_asset_id,producing_activity,truth_eligibility,first_seen_at,source_lineage,task_lineage,independent_evidence_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
      ).bind(body.media_asset_id,body.raw_sha256,body.object_key,body.object_size,
        body.normalized_pixel_hash,body.perceptual_fingerprint,body.width,body.height,body.mime,
        body.provenance_class,body.provenance_confidence,body.earlier_source_status,parentId,
        body.producing_activity,body.truth_eligibility,body.first_seen_at,body.source_lineage,
        body.task_lineage,body.independent_evidence_id || null).run();
    } catch (error) {
      const raced = await db.prepare("SELECT media_asset_id,source_lineage FROM media_asset WHERE raw_sha256=?")
        .bind(body.raw_sha256).first();
      if (raced) {
        if (raced.source_lineage !== body.source_lineage) throw new Error("MEDIA_SOURCE_LINEAGE_CONFLICT");
        return {state: "EXACT_DUPLICATE", media_asset_id: raced.media_asset_id};
      }
      throw error;
    }
    return {state: "RECORDED", media_asset_id: body.media_asset_id};
  }
  if (path === "/internal/control/workbench-write-claim") {
    required(body, ["claim_id", "file_id", "preimage_version", "preimage_sha256", "intent_sha256", "task_id"]);
    const existing = await db.prepare(
      "SELECT claim_id,intent_sha256,state,postwrite_version,postwrite_sha256,result_state FROM workbench_write_claim WHERE file_id=? AND preimage_version=?",
    ).bind(body.file_id, body.preimage_version).first();
    if (existing) {
      if (existing.claim_id !== body.claim_id || existing.intent_sha256 !== body.intent_sha256) {
        return {state: "HOLD_CONFLICT", blocker: "WORKBENCH_PREIMAGE_ALREADY_CLAIMED"};
      }
      return {state: existing.state === "COMPLETED" ? "IDEMPOTENT_SUCCESS" : existing.state,
        claim_id: existing.claim_id, postwrite_version: existing.postwrite_version,
        postwrite_sha256: existing.postwrite_sha256, result_state: existing.result_state};
    }
    await db.prepare(
      "INSERT INTO workbench_write_claim(claim_id,file_id,preimage_version,preimage_sha256,intent_sha256,task_id,state,claimed_at) VALUES(?,?,?,?,?,?,'CLAIMED',?)",
    ).bind(body.claim_id,body.file_id,body.preimage_version,body.preimage_sha256,body.intent_sha256,body.task_id,new Date().toISOString()).run();
    return {state: "CLAIMED", claim_id: body.claim_id};
  }
  if (path === "/internal/control/workbench-write-complete") {
    required(body, ["claim_id", "postwrite_version", "postwrite_sha256", "result_state"]);
    const row = await db.prepare("SELECT state FROM workbench_write_claim WHERE claim_id=?").bind(body.claim_id).first();
    if (!row) throw new Error("WORKBENCH_WRITE_CLAIM_MISSING");
    if (row.state === "COMPLETED") return {state: "IDEMPOTENT_SUCCESS", claim_id: body.claim_id};
    if (row.state !== "CLAIMED") throw new Error("WORKBENCH_WRITE_CLAIM_NOT_OPEN");
    await db.prepare(
      "UPDATE workbench_write_claim SET state='COMPLETED',completed_at=?,postwrite_version=?,postwrite_sha256=?,result_state=? WHERE claim_id=? AND state='CLAIMED'",
    ).bind(new Date().toISOString(),body.postwrite_version,body.postwrite_sha256,body.result_state,body.claim_id).run();
    return {state: "COMPLETED", claim_id: body.claim_id};
  }
  if (path === "/internal/control/workbench-write-fail") {
    required(body, ["claim_id", "blocker"]);
    await db.prepare(
      "UPDATE workbench_write_claim SET state='FAILED',completed_at=?,blocker=? WHERE claim_id=? AND state='CLAIMED'",
    ).bind(new Date().toISOString(),body.blocker,body.claim_id).run();
    return {state: "FAILED", claim_id: body.claim_id, blocker: body.blocker};
  }
  if (path === "/internal/control/inventory-observation") {
    required(body, ["observation_id", "source_revision", "observed_at"]);
    const rows = Array.isArray(body.rows) ? body.rows : [];
    for (const row of rows) {
      if (!Number.isInteger(row.row_number) || row.row_number < 1) throw new Error("INVALID_ROW_NUMBER");
    }
    const semanticPayload = canonicalJson({
      source_revision: body.source_revision,
      payload: body.payload || {},
      rows: rows.map(row => ({row_number: row.row_number, payload: row.payload || {}})),
    });
    const existing = await db.prepare(
      "SELECT source_revision,payload FROM inventory_source_observation WHERE id=?",
    ).bind(body.observation_id).first();
    if (existing) {
      if (existing.source_revision !== body.source_revision || existing.payload !== semanticPayload) collision();
      return {state: "IDEMPOTENT_SUCCESS", observation_id: body.observation_id, row_count: rows.length};
    }
    const statements = [db.prepare(
      "INSERT INTO inventory_source_observation(id,source_revision,payload,observed_at) VALUES(?,?,?,?)",
    ).bind(body.observation_id, body.source_revision, semanticPayload, body.observed_at)];
    for (const row of rows) {
      statements.push(db.prepare(
        "INSERT INTO inventory_vehicle_row(id,observation_id,payload) VALUES(?,?,?)",
      ).bind(`${body.observation_id}:row:${row.row_number}`, body.observation_id, canonicalJson(row.payload || {})));
    }
    try {
      await db.batch(statements);
    } catch (error) {
      const raced = await db.prepare(
        "SELECT source_revision,payload FROM inventory_source_observation WHERE id=?",
      ).bind(body.observation_id).first();
      if (!raced || raced.source_revision !== body.source_revision || raced.payload !== semanticPayload) throw error;
      return {state: "IDEMPOTENT_SUCCESS", observation_id: body.observation_id, row_count: rows.length};
    }
    return {state: "RECORDED", observation_id: body.observation_id, row_count: rows.length};
  }
  if (path === "/internal/control/coverage-work") {
    required(body, ["work_id", "scope_key"]);
    const existing = await db.prepare(
      "SELECT scope_key,state FROM vehicle_coverage_work WHERE id=?",
    ).bind(body.work_id).first();
    if (existing) {
      if (existing.scope_key !== body.scope_key) collision();
      return {state: "IDEMPOTENT_SUCCESS", work_id: body.work_id, work_state: existing.state};
    }
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
    const semanticPayload = canonicalJson({
      work_id: body.work_id,
      receipt_id: body.receipt_id,
      receipt: body.receipt,
      revision: body.revision || {},
      facts: body.facts,
    });
    const existing = await db.prepare(
      "SELECT work_id,state,payload FROM vehicle_configuration_revision WHERE id=?",
    ).bind(body.revision_id).first();
    if (existing) {
      if (existing.work_id !== body.work_id || existing.state !== "VERIFIED" || existing.payload !== semanticPayload) collision();
      return {state: "IDEMPOTENT_SUCCESS", revision_id: body.revision_id};
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
      ).bind(body.revision_id, body.work_id, "VERIFIED", semanticPayload),
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
    const previous = await db.prepare(
      "SELECT snapshot_id,promoted_at FROM vehicle_snapshot_promotion WHERE id=?",
    ).bind(body.promotion_id).first();
    if (previous) {
      if (previous.snapshot_id !== body.snapshot_id || previous.promoted_at !== body.promoted_at) collision();
      return {state: "IDEMPOTENT_SUCCESS", snapshot_id: body.snapshot_id};
    }
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
    "/internal/control/workbench-write-claim",
    "/internal/control/workbench-write-complete",
    "/internal/control/workbench-write-fail",
    "/internal/control/inventory-observation",
    "/internal/control/coverage-work",
    "/internal/control/verified-revision",
    "/internal/control/snapshot-promote",
    "/internal/control/media-asset",
    "/internal/control/media-object-probe",
    "/internal/control/creative-media-ref",
  ]);
  try {
    if (url.pathname === "/internal/media-schema/readback") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      const db = database(env);
      const versions = await db.prepare("SELECT version FROM schema_migrations ORDER BY version").all();
      const entries = await db.prepare(
        "SELECT name,sql FROM sqlite_master WHERE name IN ('media_asset','creative_media_ref','media_asset_source_lineage_idx')",
      ).all();
      const objects = Object.fromEntries(entries.results.map(row => [row.name, row.sql]));
      const columns = {};
      for (const name of ["media_asset", "creative_media_ref"]) {
        if (objects[name]) {
          const result = await db.prepare(`PRAGMA table_info(${name})`).all();
          columns[name] = result.results.map(row => row.name);
        }
      }
      return json({state: "READBACK", revisions: versions.results.map(row => row.version),
        objects, columns});
    }
    if (url.pathname === "/internal/creative-media-ref/read") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      const id = url.searchParams.get("creative_ref_id");
      if (!id) return json({error: "CREATIVE_REF_ID_REQUIRED"}, 400);
      const row = await database(env).prepare(
        "SELECT * FROM creative_media_ref WHERE creative_ref_id=?",
      ).bind(id).first();
      if (!row) return json({state: "MISS"});
      return json({state: "HIT", ref: {...row, channels: JSON.parse(row.channels_json)}});
    }
    if (url.pathname === "/internal/media-asset/read") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      const db = database(env);
      const selection = url.searchParams.get("raw_sha256") ?
        ["raw_sha256", url.searchParams.get("raw_sha256")] :
        ["media_asset_id", url.searchParams.get("media_asset_id")];
      if (!selection[1]) return json({error: "MEDIA_LOOKUP_REQUIRED"}, 400);
      const row = await db.prepare(`SELECT * FROM media_asset WHERE ${selection[0]}=?`)
        .bind(selection[1]).first();
      if (!row) return json({state: "MISS"});
      return json({state: "HIT", asset: row});
    }
    if (url.pathname === "/internal/media-object/read") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      const key = url.searchParams.get("object_key");
      if (!key || !/^media\/sha256\/[0-9a-f]{64}$/.test(key))
        return json({error: "MEDIA_OBJECT_KEY_INVALID"}, 400);
      const object = await mediaBucket(env).get(key);
      if (!object) return json({state: "HOLD", blocker: "MEDIA_OBJECT_MISSING"}, 503);
      return new Response(await object.arrayBuffer(), {headers: {"content-type": "application/octet-stream"}});
    }
    if (url.pathname === "/internal/media-asset/candidates") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      const lineage = url.searchParams.get("source_lineage");
      if (!lineage) return json({error: "MEDIA_SCOPE_REQUIRED"}, 400);
      const rows = await database(env).prepare(
        "SELECT media_asset_id FROM media_asset WHERE source_lineage=? ORDER BY first_seen_at LIMIT 101",
      ).bind(lineage).all();
      return json({state: "HIT", media_asset_ids: rows.results.map(row => row.media_asset_id),
        truncated: rows.results.length > 100});
    }
    if (controlPaths.has(url.pathname)) {
      if (!controlAuthorized(request, env)) return json({error: "CONTROL_AUTH_REQUIRED"}, 403);
      const body = await request.json();
      if (rejectInjection(body)) return json({error: "DIRECT_AUTHORITY_INJECTION"}, 400);
      return json(await control(database(env), url.pathname, body, env));
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

export async function handleScheduled(event, env, _ctx, fetcher = fetch) {
  if (!env.RENDER_RECONCILIATION_SHARED_SECRET) throw new Error("RECONCILIATION_SECRET_REQUIRED");
  if (!Number.isFinite(event.scheduledTime)) throw new Error("SCHEDULED_TIME_REQUIRED");
  const db = database(env);
  const scheduledAt = new Date(event.scheduledTime).toISOString();
  const runId = `cf-${event.scheduledTime}`;
  const reconciliationBody = JSON.stringify({
    operation: "vehicle-knowledge-reconcile",
    run_id: runId,
    scheduled_at: scheduledAt,
  });
  const bodyDigest = await sha256Hex(reconciliationBody);
  const claimedAt = new Date().toISOString();
  const claim = await db.prepare(
    "INSERT OR IGNORE INTO vehicle_reconciliation_run(run_id,scheduled_at,body_digest,state,claimed_at,completed_at,result_state) VALUES(?,?,?,'CLAIMED',?,NULL,NULL)",
  ).bind(runId, scheduledAt, bodyDigest, claimedAt).run();
  if (!claim.meta || claim.meta.changes !== 1) {
    const existing = await db.prepare(
      "SELECT scheduled_at,body_digest,state,result_state FROM vehicle_reconciliation_run WHERE run_id=?",
    ).bind(runId).first();
    if (!existing || existing.scheduled_at !== scheduledAt || existing.body_digest !== bodyDigest) {
      throw new Error("SCHEDULER_RUN_COLLISION");
    }
    return {state: "DUPLICATE_SUPPRESSED", run_id: runId};
  }
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
  try {
    const response = await fetcher(reconciliationUrl, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-vehicle-control-signature": signature,
      },
      body: reconciliationBody,
    });
    let result;
    try {
      result = await response.json();
    } catch (_error) {
      throw new Error(
        response.ok ? "RECONCILIATION_RECEIPT_INVALID" : "RENDER_RECONCILIATION_FAILED",
      );
    }
    if (!response.ok) {
      throw new Error(result?.blocker || "RENDER_RECONCILIATION_FAILED");
    }
    if (result?.status !== "PASS") {
      throw new Error(result?.blocker || "RECONCILIATION_RESULT_NOT_PASS");
    }
    const receipt = result.control_receipt;
    if (receipt?.row_count === 0) throw new Error("INVENTORY_OBSERVATION_EMPTY");
    if (
      typeof result.observation_id !== "string" || !result.observation_id.trim()
      || typeof result.source_revision !== "string" || !result.source_revision.trim()
      || !receipt
      || !["RECORDED", "IDEMPOTENT_SUCCESS"].includes(receipt.state)
      || !Number.isInteger(receipt.row_count) || receipt.row_count <= 0
    ) {
      throw new Error("RECONCILIATION_RECEIPT_INVALID");
    }
    await db.prepare(
      "UPDATE vehicle_reconciliation_run SET state='COMPLETED',completed_at=?,result_state='PASS' WHERE run_id=? AND state='CLAIMED'",
    ).bind(new Date().toISOString(), runId).run();
    return {state: "COMPLETED", run_id: runId};
  } catch (error) {
    await db.prepare(
      "UPDATE vehicle_reconciliation_run SET state='FAILED',completed_at=?,result_state=? WHERE run_id=? AND state='CLAIMED'",
    ).bind(new Date().toISOString(), error.message || "RENDER_RECONCILIATION_FAILED", runId).run();
    throw error;
  }
}

export default {fetch: handleRequest, scheduled: handleScheduled};
