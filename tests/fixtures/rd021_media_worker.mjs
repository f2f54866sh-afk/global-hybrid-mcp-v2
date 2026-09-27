import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {handleRequest} from "../../infra/vehicle_knowledge/worker.js";

const assets = new Map();
const db = {
  prepare(sql) {
    let values = [];
    return {
      bind(...items) { values = items; return this; },
      async first() {
        if (sql.includes("WHERE raw_sha256=?")) {
          return [...assets.values()].find(item => item.raw_sha256 === values[0]) || null;
        }
        if (sql.includes("WHERE media_asset_id=?")) return assets.get(values[0]) || null;
        throw new Error(`UNEXPECTED_QUERY:${sql}`);
      },
      async all() {
        if (!sql.includes("WHERE source_lineage=?")) throw new Error(`UNEXPECTED_LIST:${sql}`);
        return {results: [...assets.values()].filter(item => item.source_lineage === values[0])
          .map(item => ({media_asset_id: item.media_asset_id}))};
      },
      async run() {
        if (!sql.startsWith("INSERT INTO media_asset(")) throw new Error(`UNEXPECTED_WRITE:${sql}`);
        if (assets.has(values[0])) throw new Error("D1_PK_CONFLICT");
        const names = sql.slice("INSERT INTO media_asset(".length, sql.indexOf(") VALUES"))
          .split(",");
        assets.set(values[0], Object.fromEntries(names.map((name, index) => [name, values[index]])));
        return {success: true};
      },
    };
  },
  batch() { throw new Error("UNEXPECTED_BATCH"); },
};
const env = {DB: db, CONTROL_PLANE_WRITE_SECRET: "write", RUNTIME_READ_SECRET: "read"};
const request = (path, secret, body) => handleRequest(new Request(`https://worker.test${path}`, {
  method: body ? "POST" : "GET",
  headers: {authorization: `Bearer ${secret}`, "content-type": "application/json"},
  body: body ? JSON.stringify(body) : undefined,
}), env);
const raw = Buffer.from("server-owned-raw-media");
const hash = createHash("sha256").update(raw).digest("hex");
const original = {
  media_asset_id: `media:${hash}`, raw_sha256: hash,
  normalized_pixel_hash: "0".repeat(64), perceptual_fingerprint: "0".repeat(16),
  width: 10, height: 10, mime: "image/png", provenance_class: "ORIGINAL_EVIDENCE",
  parent_asset_id: null, producing_activity: "ORIGINAL_CAPTURE",
  truth_eligibility: "TRUTH_ELIGIBLE", first_seen_at: "2026-09-27T00:00:00Z",
  source_lineage: "vehicle:a", task_lineage: "turn:1",
  independent_evidence_id: `media:${hash}`, raw_base64: raw.toString("base64"),
};
assert.equal((await request("/internal/control/media-asset", "wrong", original)).status, 403);
let response = await request("/internal/control/media-asset", "write", original);
assert.equal((await response.json()).state, "RECORDED");
response = await request("/internal/control/media-asset", "write", original);
assert.deepEqual(await response.json(), {state: "EXACT_DUPLICATE", media_asset_id: original.media_asset_id});
response = await request(`/internal/media-asset/read?media_asset_id=${original.media_asset_id}`, "read");
const readback = await response.json();
assert.equal(readback.asset.raw_sha256, hash);
assert.equal(readback.raw_base64, original.raw_base64);
response = await request("/internal/media-asset/candidates?source_lineage=vehicle%3Aa", "read");
assert.deepEqual((await response.json()).media_asset_ids, [original.media_asset_id]);

const fakeRaw = Buffer.from("creative-raw-media");
const fakeHash = createHash("sha256").update(fakeRaw).digest("hex");
const edited = {...original, media_asset_id: `media:${fakeHash}`, raw_sha256: fakeHash,
  raw_base64: fakeRaw.toString("base64"), provenance_class: "AI_EDITED",
  producing_activity: "AI_EDIT", parent_asset_id: original.media_asset_id,
  truth_eligibility: "TRUTH_FORBIDDEN"};
response = await request("/internal/control/media-asset", "write", edited);
assert.equal((await response.json()).state, "RECORDED");
const childRaw = Buffer.from("resized-creative");
const childHash = createHash("sha256").update(childRaw).digest("hex");
const illegal = {...edited, media_asset_id: `media:${childHash}`, raw_sha256: childHash,
  raw_base64: childRaw.toString("base64"), provenance_class: "DERIVATIVE_RESIZE",
  producing_activity: "RESIZE", parent_asset_id: edited.media_asset_id,
  truth_eligibility: "TRUTH_ELIGIBLE"};
response = await request("/internal/control/media-asset", "write", illegal);
assert.equal((await response.json()).blocker, "MEDIA_FORBIDDEN_LINEAGE_UPGRADE");
assert.equal(assets.size, 2);
console.log("media-worker-ok");
