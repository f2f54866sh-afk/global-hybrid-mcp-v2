import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../src/global_hybrid_v2/adapters/ai_workbench_entry.html',
  import.meta.url), 'utf8');
const script = html.match(/<script type="module">([\s\S]*?)<\/script>/)?.[1];
assert.ok(script);
assert.ok(html.includes('送出並同步 AI 車源表'));
assert.ok(!html.includes('sendFollowUpMessage'));

async function scenario(truth, files = [{name:'registration.pdf', type:'application/pdf'}],
  chooseVehicle = true) {
  const elements = Object.fromEntries(['#task-text','#vehicle-select','#evidence-file','#submit','#execution',
    '#terminal','#result'].map((name) => [name, {textContent:'', disabled:false, listeners:{},
      addEventListener(kind, listener) { this.listeners[kind] = listener; }}]));
  elements['#vehicle-select'].options = [];
  elements['#vehicle-select'].appendChild = (option) =>
    elements['#vehicle-select'].options.push(option);
  elements['#task-text'].value = 'update this company vehicle';
  elements['#evidence-file'].files = files;
  const calls = [];
  const listeners = {};
  const parent = {postMessage(message) {
    if (message.method === 'tools/call') calls.push(message.params);
    queueMicrotask(() => listeners.message({source:parent, data:{jsonrpc:'2.0', id:message.id,
      result:message.method === 'tools/call' ? {structuredContent:
        message.params.name === 'list_ai_workbench_vehicle_candidates'
          ? {candidates:[{display_label:'2018 BMW 318I',
              opaque_selection_token:'signed-token'}]} : truth} : {}}}));
  }};
  const window = {parent, openai:{
    uploadFile:async (file) => ({fileId:`file-${file.name}`}),
    getFileDownloadUrl:async ({fileId}) => ({downloadUrl:
      `https://files.oaiusercontent.com/${fileId}`}),
  }, addEventListener(kind, listener) { listeners[kind] = listener; }};
  vm.runInNewContext(script, {window, document:{querySelector:(name) => elements[name],
    createElement:() => ({value:'', textContent:''})},
    Promise, Map, queueMicrotask});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(elements['#vehicle-select'].value, undefined);
  if (chooseVehicle)
    elements['#vehicle-select'].value = elements['#vehicle-select'].options[0].value;
  await elements['#submit'].listeners.click();
  return {elements, calls};
}

for (const [terminal, text, expected] of [
  ['WRITE_AND_READBACK_PASS', 'Sales answer', 'AI 車源表已完成寫入並讀回確認'],
  ['NO_DELTA', 'model claims a write', '沒有新的 AI 車源表變更'],
  ['PERSISTENCE_CAPABILITY_DEBT', '同步能力目前不可用', '同步能力目前不可用'],
  ['HOLD_CONFLICT', '資料衝突暫停', '資料衝突暫停'],
]) {
  const {elements, calls} = await scenario({execution_state:'TERMINAL',
    terminal_disposition:terminal, result_text:text});
  assert.equal(calls.length, 2);
  assert.equal(calls[0].name, 'list_ai_workbench_vehicle_candidates');
  assert.equal(calls[1].name, 'execute_controlled_sales_turn');
  assert.equal(calls[1].arguments.evidence_file.length, 1);
  assert.equal(calls[1].arguments.target_selection_token, 'signed-token');
  assert.equal(elements['#terminal'].textContent, terminal);
  assert.ok(elements['#result'].textContent.includes(expected));
  if (terminal !== 'WRITE_AND_READBACK_PASS')
    assert.ok(!elements['#result'].textContent.includes('已完成寫入'));
}

const failed = await scenario({execution_state:'EXECUTION_FAIL',
  terminal_disposition:null, result_text:'model says synchronized'});
assert.equal(failed.elements['#execution'].textContent, 'EXECUTION_FAIL');
assert.ok(!failed.elements['#result'].textContent.includes('synchronized'));

const unselected = await scenario(null, undefined, false);
assert.equal(unselected.calls.length, 1);
assert.equal(unselected.calls[0].name, 'list_ai_workbench_vehicle_candidates');
assert.equal(unselected.elements['#result'].textContent, 'TARGET_VEHICLE_SELECTION_REQUIRED');

const multiple = await scenario({execution_state:'PERSISTENCE_CAPABILITY_DEBT',
  terminal_disposition:'PERSISTENCE_CAPABILITY_DEBT',
  result_text:'MULTI_EVIDENCE_BINDING_CAPABILITY_DEBT'},
[{name:'a.png', type:'image/png'}, {name:'b.png', type:'image/png'}]);
assert.equal(multiple.calls[1].arguments.evidence_file.length, 2);
assert.equal(multiple.elements['#result'].textContent,
  'MULTI_EVIDENCE_BINDING_CAPABILITY_DEBT');
console.log('rd021-n3a-widget-ok');
