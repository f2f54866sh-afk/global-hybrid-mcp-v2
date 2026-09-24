const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });

const authorized = (request, env) => {
  const supplied = request.headers.get("authorization");
  return Boolean(env.CONTROL_TOKEN) && supplied === `Bearer ${env.CONTROL_TOKEN}`;
};

async function transactionFalsifier(env) {
  await env.DB.prepare("DELETE FROM preflight_tx WHERE id = ?").bind("A").run();
  let batchFailed = false;
  try {
    await env.DB.batch([
      env.DB.prepare("INSERT INTO preflight_tx(id, value) VALUES (?, ?)").bind("A", "one"),
      env.DB.prepare("INSERT INTO preflight_tx(id, value) VALUES (?, ?)").bind("A", "duplicate"),
    ]);
  } catch {
    batchFailed = true;
  }
  const row = await env.DB.prepare(
    "SELECT COUNT(*) AS count FROM preflight_tx WHERE id = ?",
  ).bind("A").first();
  return { batch_failed: batchFailed, residual_rows: Number(row?.count ?? -1) };
}

const RENDER_HEALTH_URL = "https://global-hybrid-mcp-v2.onrender.com/health";
const RENDER_TARGET_ID = "GLOBAL_HYBRID_RENDER_HEALTH";

async function probeRenderHealth(env, scheduledTime) {
  const probeId = `render-health:${scheduledTime}`;
  const observedAt = new Date().toISOString();
  let httpStatus = 0;
  let healthOk = false;
  try {
    const response = await fetch(RENDER_HEALTH_URL, {
      method: "GET",
      headers: { accept: "application/json" },
    });
    httpStatus = response.status;
    if (response.status === 200) {
      const body = await response.json();
      healthOk = body?.ok === true;
    }
  } catch {
    healthOk = false;
  }
  await env.DB.prepare(
    `INSERT INTO scheduler_probe_receipt (
       probe_id, scheduled_at, target_id, http_status, health_ok, attempt_count, observed_at
     ) VALUES (?, ?, ?, ?, ?, 1, ?)
     ON CONFLICT(probe_id) DO UPDATE SET
       http_status = excluded.http_status,
       health_ok = excluded.health_ok,
       attempt_count = scheduler_probe_receipt.attempt_count + 1,
       observed_at = excluded.observed_at`,
  ).bind(
    probeId,
    new Date(scheduledTime).toISOString(),
    RENDER_TARGET_ID,
    httpStatus,
    healthOk ? 1 : 0,
    observedAt,
  ).run();
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, mode: env.PREFLIGHT_MODE });
    }
    if (request.method === "GET" && url.pathname === "/d1-readback") {
      const tx = await env.DB.prepare("SELECT COUNT(*) AS count FROM preflight_tx").first();
      const probeCount = await env.DB.prepare(
        "SELECT COUNT(*) AS count FROM scheduler_probe_receipt",
      ).first();
      const latestProbe = await env.DB.prepare(
        `SELECT probe_id, scheduled_at, target_id, http_status, health_ok,
                attempt_count, observed_at
           FROM scheduler_probe_receipt
          ORDER BY scheduled_at DESC LIMIT 1`,
      ).first();
      return json({
        database: "vehicle-knowledge-preflight",
        tx_rows: Number(tx.count),
        scheduler_probe_count: Number(probeCount.count),
        latest_scheduler_probe: latestProbe,
      });
    }
    if (request.method === "POST" && url.pathname === "/dispatch-test") {
      if (!authorized(request, env)) return json({ error: "CONTROL_AUTH_REQUIRED" }, 403);
      const result = await transactionFalsifier(env);
      return json(result, result.batch_failed && result.residual_rows === 0 ? 200 : 500);
    }
    return json({ error: "NOT_FOUND" }, 404);
  },

  async scheduled(controller, env) {
    await probeRenderHealth(env, controller.scheduledTime);
  },
};
