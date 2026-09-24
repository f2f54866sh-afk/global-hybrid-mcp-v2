const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {"content-type": "application/json"},
});

const bearer = request => request.headers.get("authorization") || "";
const controlAuthorized = (request, env) => bearer(request) === `Bearer ${env.CONTROL_PLANE_WRITE_SECRET}`;
const readAuthorized = (request, env) => bearer(request) === `Bearer ${env.RUNTIME_READ_SECRET}`;
const rejectInjection = body => ["sql", "table", "spreadsheet_id", "verified", "promoted", "authority_state"].some(key => key in body);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const controlPaths = new Set([
      "/internal/control/inventory-observation",
      "/internal/control/coverage-work",
      "/internal/control/verified-revision",
      "/internal/control/snapshot-promote",
    ]);
    if (controlPaths.has(url.pathname)) {
      if (!controlAuthorized(request, env)) return json({error: "CONTROL_AUTH_REQUIRED"}, 403);
      const body = await request.json();
      if (rejectInjection(body)) return json({error: "DIRECT_AUTHORITY_INJECTION"}, 400);
      return json(await env.VEHICLE_CONTROL.handle(url.pathname, body));
    }
    if (url.pathname === "/v1/vehicle-config/query" || url.pathname === "/v1/vehicle-config/readback") {
      if (!readAuthorized(request, env)) return json({error: "RUNTIME_READ_AUTH_REQUIRED"}, 403);
      return json(await env.VEHICLE_READ.handle(url.pathname, Object.fromEntries(url.searchParams)));
    }
    return json({error: "NOT_FOUND"}, 404);
  },
};
