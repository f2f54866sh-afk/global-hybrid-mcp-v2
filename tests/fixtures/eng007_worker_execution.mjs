import assert from "node:assert/strict";
import {handleRequest, handleScheduled} from "../../infra/vehicle_knowledge/worker.js";

class Statement {
  constructor(db, sql) { this.db = db; this.sql = sql; this.values = []; }
  bind(...values) { this.values = values; return this; }
  async first() {
    if (this.sql.includes("vehicle_coverage_work WHERE id")) {
      return this.db.tables.work.get(this.values[0]) || null;
    }
    if (this.sql.includes("vehicle_snapshot_build WHERE id")) {
      return this.db.tables.build.get(this.values[0]) || null;
    }
    if (this.sql.includes("vehicle_snapshot_active a JOIN")) {
      const active = this.db.tables.active;
      if (!active) return null;
      const build = this.db.tables.build.get(active.snapshot_id);
      return {...active, ...build};
    }
    throw new Error("UNEXPECTED_D1_QUERY");
  }
  async run() {
    const [first, second, third] = this.values;
    if (this.sql.includes("INSERT INTO vehicle_coverage_work")) {
      if (this.db.tables.work.has(first)) throw new Error("D1_CONFLICT");
      this.db.tables.work.set(first, {scope_key: second, state: third});
    } else if (this.sql.includes("INSERT INTO vehicle_snapshot_promotion")) {
      this.db.tables.promotion.set(first, {snapshot_id: second, promoted_at: third});
    } else if (this.sql.includes("INSERT INTO vehicle_snapshot_active")) {
      this.db.tables.active = {snapshot_id: first, promotion_id: second};
    } else if (this.sql.includes("UPDATE vehicle_coverage_work")) {
      const work = this.db.tables.work.get(first);
      if (!work || work.state !== "OPEN") throw new Error("D1_CONFLICT");
      work.state = "VERIFIED";
    } else if (this.sql.startsWith("INSERT INTO")) {
      // Other fixed-schema writes are accepted by this D1-compatible harness.
    } else {
      throw new Error("UNEXPECTED_D1_MUTATION");
    }
    return {success: true};
  }
}

class D1Harness {
  constructor() {
    this.tables = {work: new Map(), build: new Map(), promotion: new Map(), active: null};
  }
  prepare(sql) { return new Statement(this, sql); }
  async batch(statements) {
    const before = structuredClone(this.tables);
    try { return await Promise.all(statements.map(statement => statement.run())); }
    catch (error) { this.tables = before; throw error; }
  }
}

const db = new D1Harness();
db.tables.build.set("snapshot-1", {
  id: "snapshot-1",
  builder_version: "builder-1",
  payload: JSON.stringify({
    source_revision: "revision-1",
    generated_at: "2026-09-24T00:00:00Z",
    configurations: [{
      configuration_id: "tiguan-r-2021",
      market: "TW", model_year: 2021, make: "VW", model: "TIGUAN R",
      generation: null, trim: "R", powertrain: {}, equipment: [],
      primary_source_pointers: ["source:1"], last_verified: "2026-09-24",
      conflict_state: "NONE", query_key: "TW|2021|VW|TIGUAN R",
    }],
  }),
});
const env = {DB: db, CONTROL_PLANE_WRITE_SECRET: "write", RUNTIME_READ_SECRET: "read"};

const call = (path, token, init = {}) => handleRequest(new Request(`https://worker.test${path}`, {
  method: init.method || "GET",
  headers: {authorization: `Bearer ${token}`, "content-type": "application/json"},
  body: init.body ? JSON.stringify(init.body) : undefined,
}), env);

assert.equal((await call("/v1/vehicle-config/readback", "bad")).status, 403);
assert.equal((await call("/internal/control/coverage-work", "read", {method: "POST", body: {}})).status, 403);
assert.equal((await handleRequest(new Request("https://worker.test/v1/vehicle-config/readback", {
  headers: {authorization: "Bearer read"},
}), {...env, DB: undefined})).status, 503);

let response = await call("/internal/control/coverage-work", "write", {
  method: "POST", body: {work_id: "work-1", scope_key: "TW|2021|VW|TIGUAN R"},
});
assert.equal(response.status, 200);
response = await call("/internal/control/snapshot-promote", "write", {
  method: "POST", body: {snapshot_id: "missing", promotion_id: "bad", promoted_at: "now"},
});
assert.equal(response.status, 503);
response = await call("/internal/control/snapshot-promote", "write", {
  method: "POST", body: {snapshot_id: "snapshot-1", promotion_id: "promotion-1", promoted_at: "2026-09-24T00:00:01Z"},
});
assert.equal(response.status, 200);

response = await call("/v1/vehicle-config/readback", "read");
assert.equal(response.status, 200);
assert.equal((await response.json()).snapshot_id, "snapshot-1");
response = await call("/v1/vehicle-config/query?market=TW&model_year=2021&make=VW&model=TIGUAN%20R", "read");
const query = await response.json();
assert.equal(query.state, "HIT");
assert.equal(query.configurations[0].configuration_id, "tiguan-r-2021");

response = await call("/internal/control/coverage-work", "write", {
  method: "POST", body: {work_id: "work-2", scope_key: "scope", table: "caller"},
});
assert.equal(response.status, 400);

let scheduledCall;
await handleScheduled({}, {RENDER_RECONCILIATION_SHARED_SECRET: "secret"}, {}, async (url, init) => {
  scheduledCall = {url, init};
  return {ok: true};
});
assert.equal(
  scheduledCall.url,
  "https://global-hybrid-mcp-v2.onrender.com/internal/vehicle-knowledge/reconcile",
);
assert.equal(scheduledCall.init.body, '{"operation":"vehicle-knowledge-reconcile"}');
assert.match(scheduledCall.init.headers["x-vehicle-control-signature"], /^[0-9a-f]{64}$/);
await assert.rejects(
  handleScheduled({}, {RENDER_RECONCILIATION_SHARED_SECRET: "secret"}, {}, async () => ({ok: false})),
  /RENDER_RECONCILIATION_FAILED/,
);
await assert.rejects(handleScheduled({}, {}, {}, async () => ({ok: true})), /SECRET_REQUIRED/);

console.log("ENG007_WORKER_EXECUTION_BINDING_PASS");
