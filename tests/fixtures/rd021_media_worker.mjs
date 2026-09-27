import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {handleRequest} from "../../infra/vehicle_knowledge/worker.js";

const assets = new Map();
const objects = new Map();
const etags = new Map();
let objectVersion = 0;
const creativeRefs = new Map();
const db = {
  prepare(sql) {
    let values = [];
    return {
      bind(...items) { values = items; return this; },
      async first() {
        if (sql.includes("creative_media_ref WHERE creative_ref_id=?"))
          return creativeRefs.get(values[0]) || null;
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
        if (sql.startsWith("INSERT INTO creative_media_ref(")) {
          const names = sql.slice("INSERT INTO creative_media_ref(".length, sql.indexOf(") VALUES"))
            .split(",");
          creativeRefs.set(values[0], Object.fromEntries(names.map((name, index) => [name, values[index]])));
          return {success: true};
        }
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
const env = {
  DB: db, CONTROL_PLANE_WRITE_SECRET: "write", RUNTIME_READ_SECRET: "read",
  MEDIA_BUCKET: {
    async get(key) {
      const bytes = objects.get(key);
      return bytes ? {etag: etags.get(key), arrayBuffer: async () => Uint8Array.from(bytes).buffer} : null;
    },
    async put(key, bytes, options) {
      const condition = options?.onlyIf;
      if (condition instanceof Headers && condition.get("If-None-Match") === "*" && objects.has(key))
        return null;
      if (condition?.etagMatches && etags.get(key) !== condition.etagMatches) return null;
      objects.set(key, Uint8Array.from(bytes));
      const etag = `etag-${++objectVersion}`;
      etags.set(key, etag);
      return {etag};
    },
    async delete(key) { objects.delete(key); etags.delete(key); },
    async list({prefix}) {
      return {objects: [...objects.keys()].filter(key => key.startsWith(prefix)).map(key => ({key})),
        truncated: false};
    },
  },
};
const request = (path, secret, body) => handleRequest(new Request(`https://worker.test${path}`, {
  method: body ? "POST" : "GET",
  headers: {authorization: `Bearer ${secret}`, "content-type": "application/json"},
  body: body ? JSON.stringify(body) : undefined,
}), env);
const raw = Buffer.from("server-owned-raw-media");
const hash = createHash("sha256").update(raw).digest("hex");
const original = {
  media_asset_id: `media:${hash}`, raw_sha256: hash,
  object_key: `media/sha256/${hash}`, object_size: raw.length,
  normalized_pixel_hash: "0".repeat(64), perceptual_fingerprint: "0".repeat(16),
  width: 10, height: 10, mime: "image/png", provenance_class: "ORIGINAL_EVIDENCE",
  provenance_confidence: "VERIFIED", earlier_source_status: "UNKNOWN",
  parent_asset_id: null, producing_activity: "ORIGINAL_CAPTURE",
  truth_eligibility: "FULL", first_seen_at: "2026-09-27T00:00:00Z",
  source_lineage: "vehicle:a", task_lineage: "turn:1",
  independent_evidence_id: `media:${hash}`, raw_base64: raw.toString("base64"),
};
const probeRaw = Buffer.from("rd021-isolated-probe");
const probeHash = createHash("sha256").update(probeRaw).digest("hex");
const probe = {raw_base64: probeRaw.toString("base64"), expected_sha256: probeHash,
  deployment_id: "isolated001", nonce: "0".repeat(32),
  expected_object_key: `__probe__/rd021/isolated001/${"0".repeat(32)}`};
let probeResponse = await request("/internal/control/media-object-probe", "write", probe);
assert.equal((await probeResponse.json()).state, "PROBE_PASS");
assert.equal(objects.has(probe.expected_object_key), false);
assert.equal(assets.size, 0);
probeResponse = await request("/internal/control/media-object-probe", "write",
  {...probe, expected_object_key: `media/sha256/${probeHash}`});
assert.equal((await probeResponse.json()).blocker, "MEDIA_PROBE_OBJECT_IDENTITY_MISMATCH");
assert.equal(objects.size, 0);
probeResponse = await request("/internal/control/media-object-probe", "write", probe);
assert.equal((await probeResponse.json()).state, "PROBE_PASS");
env.MEDIA_BUCKET.delete = async () => { throw new Error("DELETE_FAILED"); };
probeResponse = await request("/internal/control/media-object-probe", "write", probe);
assert.equal((await probeResponse.json()).blocker, "HOLD_PROBE_CLEANUP_FAILED");
objects.delete(probe.expected_object_key);
env.MEDIA_BUCKET.delete = async key => { objects.delete(key); };
const journalEndpoint = "/internal/control/deployment-journal";
const journalId = "isolated001";
const journalKey = `__deployment__/rd021/${journalId}/receipts/00-CURRENT_STATE_PREFLIGHT-${"a".repeat(64)}.json`;
const journalRaw = Buffer.from('{"receipt":"signed-test-fixture"}');
const journalBase = {deployment_id: journalId, key: journalKey};
let journalResponse = await request(journalEndpoint, "write", {...journalBase,
  operation: "PUT_IMMUTABLE", raw_base64: journalRaw.toString("base64")});
let journalResult = await journalResponse.json();
assert.equal(journalResult.state, "PUT_READBACK_PASS");
const journalEtag = journalResult.etag;
journalResponse = await request(journalEndpoint, "write", {...journalBase,
  operation: "PUT_IMMUTABLE", raw_base64: journalRaw.toString("base64")});
assert.equal((await journalResponse.json()).state, "CAS_CONFLICT");
journalResponse = await request(journalEndpoint, "write", {...journalBase, operation: "GET"});
journalResult = await journalResponse.json();
assert.equal(journalResult.etag, journalEtag);
assert.deepEqual(Buffer.from(journalResult.raw_base64, "base64"), journalRaw);
journalResponse = await request(journalEndpoint, "write", {deployment_id: journalId, operation: "LIST"});
assert.deepEqual((await journalResponse.json()).keys, [journalKey]);
const headKey = `__deployment__/rd021/${journalId}/head.json`;
journalResponse = await request(journalEndpoint, "write", {deployment_id: journalId,
  operation: "CAS_HEAD", key: headKey, raw_base64: Buffer.from("head-1").toString("base64")});
journalResult = await journalResponse.json();
assert.equal(journalResult.state, "PUT_READBACK_PASS");
journalResponse = await request(journalEndpoint, "write", {deployment_id: journalId,
  operation: "CAS_HEAD", key: headKey, expected_etag: "stale",
  raw_base64: Buffer.from("head-2").toString("base64")});
assert.equal((await journalResponse.json()).state, "CAS_CONFLICT");
assert.equal(assets.size, 0);
const journalMediaResponse = await request(
  `/internal/media-object/read?object_key=${encodeURIComponent(journalKey)}`, "read");
assert.equal((await journalMediaResponse.json()).error, "MEDIA_OBJECT_KEY_INVALID");
delete env.MEDIA_BUCKET.delete;
probeResponse = await request("/internal/control/media-object-probe", "write", probe);
assert.equal((await probeResponse.json()).blocker, "MEDIA_OBJECT_STORE_REQUIRED");
env.MEDIA_BUCKET.delete = async key => { objects.delete(key); };
assert.equal((await request("/internal/control/media-asset", "wrong", original)).status, 403);
let response = await request("/internal/control/media-asset", "write", original);
assert.equal((await response.json()).state, "RECORDED");
response = await request("/internal/control/media-asset", "write", original);
assert.deepEqual(await response.json(), {state: "EXACT_DUPLICATE", media_asset_id: original.media_asset_id});
response = await request(`/internal/media-asset/read?media_asset_id=${original.media_asset_id}`, "read");
const readback = await response.json();
assert.equal(readback.asset.raw_sha256, hash);
assert.equal(readback.asset.raw_capture_base64, undefined);
assert.equal(readback.raw_base64, undefined);
assert.equal(objects.get(original.object_key).length, raw.length);
response = await request(`/internal/media-object/read?object_key=${original.object_key}`, "read");
assert.deepEqual(Buffer.from(await response.arrayBuffer()), raw);
response = await request("/internal/media-asset/candidates?source_lineage=vehicle%3Aa", "read");
assert.deepEqual((await response.json()).media_asset_ids, [original.media_asset_id]);

const fakeRaw = Buffer.from("creative-raw-media");
const fakeHash = createHash("sha256").update(fakeRaw).digest("hex");
const edited = {...original, media_asset_id: `media:${fakeHash}`, raw_sha256: fakeHash,
  object_key: `media/sha256/${fakeHash}`, object_size: fakeRaw.length,
  raw_base64: fakeRaw.toString("base64"), provenance_class: "AI_EDITED",
  producing_activity: "AI_EDIT", parent_asset_id: original.media_asset_id,
  truth_eligibility: "FORBIDDEN"};
response = await request("/internal/control/media-asset", "write", edited);
assert.equal((await response.json()).state, "RECORDED");
const creativeId = `creative:${createHash("sha256").update(`vehicle:a\0${edited.media_asset_id}`)
  .digest("hex")}`;
const creative = {creative_ref_id: creativeId, media_asset_id: edited.media_asset_id,
  vehicle_instance_id: "vehicle:a", target_column: "銷售素材Refs", channels: ["FB", "8891"]};
response = await request("/internal/control/creative-media-ref", "write", creative);
assert.equal((await response.json()).state, "RECORDED");
response = await request("/internal/control/creative-media-ref", "write", creative);
assert.equal((await response.json()).state, "IDEMPOTENT_SUCCESS");
response = await request(`/internal/creative-media-ref/read?creative_ref_id=${creativeId}`, "read");
assert.deepEqual((await response.json()).ref.channels, ["8891", "FB"]);
assert.equal(creativeRefs.size, 1);
assert.equal(assets.get(edited.media_asset_id).truth_eligibility, "FORBIDDEN");
const externalRaw = Buffer.from("external-first-observed");
const externalHash = createHash("sha256").update(externalRaw).digest("hex");
const forgedFull = {...original, media_asset_id: `media:${externalHash}`,
  raw_sha256: externalHash, object_key: `media/sha256/${externalHash}`,
  object_size: externalRaw.length, raw_base64: externalRaw.toString("base64"),
  provenance_class: "FIRST_OBSERVED_EXTERNAL", producing_activity: "FIRST_OBSERVED_EXTERNAL",
  provenance_confidence: "PARTIAL", truth_eligibility: "FULL",
  independent_evidence_id: `media:${externalHash}`};
response = await request("/internal/control/media-asset", "write", forgedFull);
assert.equal((await response.json()).blocker, "MEDIA_FIRST_OBSERVED_ESCALATION");
assert.equal(objects.has(forgedFull.object_key), false);
const childRaw = Buffer.from("resized-creative");
const childHash = createHash("sha256").update(childRaw).digest("hex");
const illegal = {...edited, media_asset_id: `media:${childHash}`, raw_sha256: childHash,
  object_key: `media/sha256/${childHash}`, object_size: childRaw.length,
  raw_base64: childRaw.toString("base64"), provenance_class: "DERIVATIVE_RESIZE",
  producing_activity: "RESIZE", parent_asset_id: edited.media_asset_id,
  truth_eligibility: "FULL"};
response = await request("/internal/control/media-asset", "write", illegal);
assert.equal((await response.json()).blocker, "MEDIA_FORBIDDEN_LINEAGE_UPGRADE");
assert.equal(assets.size, 2);
objects.delete(edited.object_key);
response = await request(`/internal/media-object/read?object_key=${edited.object_key}`, "read");
assert.equal((await response.json()).blocker, "MEDIA_OBJECT_MISSING");
console.log("media-worker-ok");
