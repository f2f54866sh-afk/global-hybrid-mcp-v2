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

async function dispatchGithub(env, eventId) {
  if (!env.GITHUB_DISPATCH_TOKEN) {
    return { ok: false, blocker: "GITHUB_DISPATCH_TOKEN_UNAVAILABLE" };
  }
  const admitted = await env.DB.prepare(
    "INSERT OR IGNORE INTO preflight_dispatch(event_id, dispatched_at) VALUES (?, ?)",
  ).bind(eventId, new Date().toISOString()).run();
  if (admitted.meta.changes !== 1) {
    return { ok: true, duplicate_suppressed: true, dispatch_count: 0 };
  }
  const url = `https://api.github.com/repos/${env.GITHUB_OWNER}/${env.GITHUB_REPO}`
    + `/actions/workflows/${env.GITHUB_WORKFLOW}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      "content-type": "application/json",
      "user-agent": "eng007-zero-cost-preflight",
      "x-github-api-version": "2022-11-28",
    },
    body: JSON.stringify({ ref: env.GITHUB_REF }),
  });
  const requestId = response.headers.get("x-github-request-id");
  await env.DB.prepare(
    "UPDATE preflight_dispatch SET github_status = ?, github_request_id = ? WHERE event_id = ?",
  ).bind(response.status, requestId, eventId).run();
  return { ok: response.status === 204, status: response.status, dispatch_count: 1, request_id: requestId };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return json({ ok: true, mode: env.PREFLIGHT_MODE });
    }
    if (request.method === "GET" && url.pathname === "/d1-readback") {
      const tx = await env.DB.prepare("SELECT COUNT(*) AS count FROM preflight_tx").first();
      const dispatch = await env.DB.prepare("SELECT COUNT(*) AS count FROM preflight_dispatch").first();
      return json({ database: "vehicle-knowledge-preflight", tx_rows: Number(tx.count), dispatch_rows: Number(dispatch.count) });
    }
    if (request.method === "POST" && url.pathname === "/dispatch-test") {
      if (!authorized(request, env)) return json({ error: "CONTROL_AUTH_REQUIRED" }, 403);
      const result = await transactionFalsifier(env);
      return json(result, result.batch_failed && result.residual_rows === 0 ? 200 : 500);
    }
    return json({ error: "NOT_FOUND" }, 404);
  },

  async scheduled(controller, env) {
    const eventId = `cron:${controller.scheduledTime}`;
    await dispatchGithub(env, eventId);
  },
};
