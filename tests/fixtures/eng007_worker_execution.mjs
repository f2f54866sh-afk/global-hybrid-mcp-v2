import assert from "node:assert/strict";
import {handleRequest, handleScheduled} from "../../infra/vehicle_knowledge/worker.js";

class Statement {
  constructor(db, sql) { this.db = db; this.sql = sql; this.values = []; }
  bind(...values) { this.values = values; return this; }
  async first() {
    const id = this.values[0];
    if (this.sql.includes("inventory_source_observation WHERE id")) return this.db.tables.observation.get(id) || null;
    if (this.sql.includes("vehicle_coverage_work WHERE id")) return this.db.tables.work.get(id) || null;
    if (this.sql.includes("vehicle_configuration_revision WHERE id")) return this.db.tables.revision.get(id) || null;
    if (this.sql.includes("vehicle_snapshot_promotion WHERE id")) return this.db.tables.promotion.get(id) || null;
    if (this.sql.includes("vehicle_reconciliation_run WHERE run_id")) return this.db.tables.run.get(id) || null;
    if (this.sql.includes("vehicle_snapshot_build WHERE id")) return this.db.tables.build.get(id) || null;
    if (this.sql.includes("vehicle_snapshot_active a JOIN")) {
      const active = this.db.tables.active;
      return active ? {...active, ...this.db.tables.build.get(active.snapshot_id)} : null;
    }
    throw new Error(`UNEXPECTED_D1_QUERY:${this.sql}`);
  }
  async run() {
    const [a, b, c, d] = this.values;
    const insert = (table, id, value) => {
      if (table.has(id)) throw new Error("D1_PK_CONFLICT");
      table.set(id, value);
    };
    if (this.sql.includes("INSERT INTO inventory_source_observation")) {
      insert(this.db.tables.observation, a, {source_revision: b, payload: c, observed_at: d});
    } else if (this.sql.includes("INSERT INTO inventory_vehicle_row")) {
      insert(this.db.tables.row, a, {observation_id: b, payload: c});
    } else if (this.sql.includes("INSERT INTO vehicle_coverage_work")) {
      insert(this.db.tables.work, a, {scope_key: b, state: c});
    } else if (this.sql.includes("INSERT INTO vehicle_fact_verification_receipt")) {
      insert(this.db.tables.receipt, a, {work_id: b, decision: c, payload: d});
    } else if (this.sql.includes("INSERT INTO vehicle_configuration_revision")) {
      insert(this.db.tables.revision, a, {work_id: b, state: c, payload: d});
    } else if (this.sql.includes("INSERT INTO vehicle_configuration_fact")) {
      insert(this.db.tables.fact, a, {revision_id: b, payload: c});
    } else if (this.sql.includes("INSERT INTO vehicle_snapshot_promotion")) {
      insert(this.db.tables.promotion, a, {snapshot_id: b, promoted_at: c});
    } else if (this.sql.includes("INSERT INTO vehicle_snapshot_active")) {
      this.db.tables.active = {snapshot_id: a, promotion_id: b};
    } else if (this.sql.includes("INSERT OR IGNORE INTO vehicle_reconciliation_run")) {
      if (this.db.tables.run.has(a)) return {success: true, meta: {changes: 0}};
      this.db.tables.run.set(a, {
        scheduled_at: b, body_digest: c, state: "CLAIMED", claimed_at: d,
        completed_at: null, result_state: null,
      });
      return {success: true, meta: {changes: 1}};
    } else if (this.sql.includes("UPDATE vehicle_reconciliation_run SET state='COMPLETED'")) {
      const run = this.db.tables.run.get(b);
      if (!run || run.state !== "CLAIMED") return {success: true, meta: {changes: 0}};
      Object.assign(run, {state: "COMPLETED", completed_at: a, result_state: "PASS"});
    } else if (this.sql.includes("UPDATE vehicle_reconciliation_run SET state='FAILED'")) {
      const run = this.db.tables.run.get(c);
      if (!run || run.state !== "CLAIMED") return {success: true, meta: {changes: 0}};
      Object.assign(run, {state: "FAILED", completed_at: a, result_state: b});
    } else if (this.sql.includes("UPDATE vehicle_coverage_work")) {
      const work = this.db.tables.work.get(a);
      if (!work || work.state !== "OPEN") throw new Error("D1_STATE_CONFLICT");
      work.state = "VERIFIED";
    } else {
      throw new Error(`UNEXPECTED_D1_MUTATION:${this.sql}`);
    }
    return {success: true, meta: {changes: 1}};
  }
}

class D1Harness {
  constructor() {
    this.tables = {
      observation: new Map(), row: new Map(), work: new Map(), receipt: new Map(),
      revision: new Map(), fact: new Map(), build: new Map(), promotion: new Map(),
      run: new Map(), active: null,
    };
  }
  prepare(sql) { return new Statement(this, sql); }
  async batch(statements) {
    const before = structuredClone(this.tables);
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.run());
      return results;
    } catch (error) {
      this.tables = before;
      throw error;
    }
  }
}

const db = new D1Harness();
db.tables.build.set("snapshot-1", {
  id: "snapshot-1", builder_version: "builder-1",
  payload: JSON.stringify({
    source_revision: "revision-1", generated_at: "2026-09-24T00:00:00Z",
    configurations: [{
      configuration_id: "tiguan-r-2021", market: "TW", model_year: 2021,
      make: "VW", model: "TIGUAN R", generation: null, trim: "R", powertrain: {},
      equipment: [], primary_source_pointers: ["source:1"], last_verified: "2026-09-24",
      conflict_state: "NONE", query_key: "TW|2021|VW|TIGUAN R",
    }],
  }),
});
const env = {DB: db, CONTROL_PLANE_WRITE_SECRET: "write", RUNTIME_READ_SECRET: "read"};
const call = (path, token, body, method = body ? "POST" : "GET") => handleRequest(
  new Request(`https://worker.test${path}`, {
    method, headers: {authorization: `Bearer ${token}`, "content-type": "application/json"},
    body: body ? JSON.stringify(body) : undefined,
  }), env,
);
const payload = response => response.json();

assert.equal((await call("/v1/vehicle-config/readback", "bad")).status, 403);
assert.equal((await handleRequest(new Request("https://worker.test/v1/vehicle-config/readback", {
  headers: {authorization: "Bearer read"},
}), {...env, DB: undefined})).status, 503);

const observationA = {
  observation_id: "observation-a", source_revision: "revision-a", observed_at: "2026-09-24T00:00:00Z",
  payload: {normalizer_version: "v1"}, rows: [{row_number: 7, payload: {model: "TIGUAN R"}}],
};
assert.equal((await call("/internal/control/inventory-observation", "write", observationA)).status, 200);
let response = await call("/internal/control/inventory-observation", "write", observationA);
assert.equal((await payload(response)).state, "IDEMPOTENT_SUCCESS");
response = await call("/internal/control/inventory-observation", "write", {
  ...observationA, rows: [{row_number: 7, payload: {model: "FORGED"}}],
});
assert.equal(response.status, 503);
assert.equal((await payload(response)).blocker, "IDENTITY_COLLISION");
const observationB = {...observationA, observation_id: "observation-b", source_revision: "revision-b"};
assert.equal((await call("/internal/control/inventory-observation", "write", observationB)).status, 200);
assert(db.tables.row.has("observation-a:row:7"));
assert(db.tables.row.has("observation-b:row:7"));

const coverage = {work_id: "work-1", scope_key: "TW|2021|VW|TIGUAN R"};
assert.equal((await call("/internal/control/coverage-work", "write", coverage)).status, 200);
response = await call("/internal/control/coverage-work", "write", coverage);
assert.equal((await payload(response)).state, "IDEMPOTENT_SUCCESS");
assert.equal((await call("/internal/control/coverage-work", "write", {
  ...coverage, scope_key: "conflicting-scope",
})).status, 503);

const verified = {
  work_id: "work-1", revision_id: "revision-verified-1", receipt_id: "receipt-1",
  receipt: {decision: "PASS"}, revision: {source: "receipt-1"},
  facts: [{fact_id: "fact-1", payload: {fact_key: "power", value: "320", unit: "PS"}}],
};
assert.equal((await call("/internal/control/verified-revision", "write", verified)).status, 200);
response = await call("/internal/control/verified-revision", "write", verified);
assert.equal((await payload(response)).state, "IDEMPOTENT_SUCCESS");
assert.equal((await call("/internal/control/verified-revision", "write", {
  ...verified, facts: [{fact_id: "fact-1", payload: {fact_key: "power", value: "999", unit: "PS"}}],
})).status, 503);

const promotion = {snapshot_id: "snapshot-1", promotion_id: "promotion-1", promoted_at: "2026-09-24T00:00:01Z"};
assert.equal((await call("/internal/control/snapshot-promote", "write", promotion)).status, 200);
response = await call("/internal/control/snapshot-promote", "write", promotion);
assert.equal((await payload(response)).state, "IDEMPOTENT_SUCCESS");
assert.equal((await call("/internal/control/snapshot-promote", "write", {
  ...promotion, promoted_at: "2026-09-24T00:00:09Z",
})).status, 503);
const activeBeforeFailure = structuredClone(db.tables.active);
assert.equal((await call("/internal/control/snapshot-promote", "write", {
  snapshot_id: "missing", promotion_id: "promotion-bad", promoted_at: "2026-09-24T00:00:02Z",
})).status, 503);
assert.deepEqual(db.tables.active, activeBeforeFailure);

response = await call("/v1/vehicle-config/readback", "read");
assert.equal((await payload(response)).snapshot_id, "snapshot-1");
response = await call("/v1/vehicle-config/query?market=TW&model_year=2021&make=VW&model=TIGUAN%20R", "read");
assert.equal((await payload(response)).state, "HIT");

const scheduledCalls = [];
const scheduledEvent = {scheduledTime: 1790208000000};
const schedulerEnv = {...env, RENDER_RECONCILIATION_SHARED_SECRET: "secret"};
await handleScheduled(scheduledEvent, schedulerEnv, {}, async (url, init) => {
  scheduledCalls.push({url, init}); return {ok: true};
});
const scheduledBody = JSON.parse(scheduledCalls[0].init.body);
assert.equal(scheduledBody.run_id, "cf-1790208000000");
assert.equal(scheduledBody.scheduled_at, "2026-09-24T00:00:00.000Z");
assert.match(scheduledCalls[0].init.headers["x-vehicle-control-signature"], /^[0-9a-f]{64}$/);
const restartedWorker = await import("../../infra/vehicle_knowledge/worker.js?restart=1");
const replay = await restartedWorker.handleScheduled(scheduledEvent, schedulerEnv, {}, async () => {
  scheduledCalls.push({unexpected: true}); return {ok: true};
});
assert.equal(replay.state, "DUPLICATE_SUPPRESSED");
assert.equal(scheduledCalls.length, 1);

const raceEvent = {scheduledTime: 1790208001000};
let raceRenderCalls = 0;
const raceResults = await Promise.all([
  handleScheduled(raceEvent, schedulerEnv, {}, async () => { raceRenderCalls += 1; return {ok: true}; }),
  handleScheduled(raceEvent, schedulerEnv, {}, async () => { raceRenderCalls += 1; return {ok: true}; }),
]);
assert.equal(raceRenderCalls, 1);
assert.deepEqual(new Set(raceResults.map(item => item.state)), new Set(["COMPLETED", "DUPLICATE_SUPPRESSED"]));

const collisionEvent = {scheduledTime: 1790208002000};
db.tables.run.set("cf-1790208002000", {
  scheduled_at: "2026-09-24T00:00:02.000Z", body_digest: "forged", state: "CLAIMED",
});
await assert.rejects(
  handleScheduled(collisionEvent, schedulerEnv, {}, async () => { throw new Error("MUST_NOT_CALL"); }),
  /SCHEDULER_RUN_COLLISION/,
);

const failedEvent = {scheduledTime: 1790208003000};
let failedRenderCalls = 0;
await assert.rejects(handleScheduled(failedEvent, schedulerEnv, {}, async () => {
  failedRenderCalls += 1; return {ok: false};
}), /RENDER_RECONCILIATION_FAILED/);
const failedReplay = await handleScheduled(failedEvent, schedulerEnv, {}, async () => {
  failedRenderCalls += 1; return {ok: true};
});
assert.equal(failedReplay.state, "DUPLICATE_SUPPRESSED");
assert.equal(failedRenderCalls, 1);

await assert.rejects(handleScheduled({}, schedulerEnv, {}, async () => ({ok: true})), /SCHEDULED_TIME_REQUIRED/);
await assert.rejects(handleScheduled(scheduledEvent, env, {}, async () => ({ok: true})), /SECRET_REQUIRED/);

console.log("ENG007_WORKER_EXECUTION_BINDING_PASS");
