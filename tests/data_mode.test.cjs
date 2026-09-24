const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

const script=fs.readFileSync(path.join(__dirname,'../app/assistant_ui/data-mode.js'),'utf8');

test('retired demo URL cannot be selected from the formal workbench',()=>{
  const location={href:'http://127.0.0.1:8890/assistant-ui/?research=abc&dataset=old#trackunit-asset=old',search:'?research=abc&dataset=old'};
  const box={location,URL,URLSearchParams,module:{exports:{}},document:{addEventListener(){},documentElement:{dataset:{}},querySelectorAll:()=>[]}};
  box.window=box;box.parent=box;
  vm.runInNewContext(script,box);
  assert.throws(()=>box.module.exports.targetUrlFor(location.href,'demo'),/Unsupported data mode/);
  assert.equal(box.module.exports.targetUrlFor(location.href,'live'),
    'http://127.0.0.1:8890/assistant-ui/?mode=live');
});

test('old demo links are canonicalized and still read live Trackunit data',async()=>{
  const calls=[],replaced=[],href='http://127.0.0.1:8890/assistant-ui/?demo=1&mode=demo';
  const box={URL,URLSearchParams,Headers,location:{href,search:'?demo=1&mode=demo',origin:'http://127.0.0.1:8890'},
    history:{replaceState:(state,title,url)=>replaced.push(url)},
    document:{addEventListener(){},documentElement:{dataset:{}},querySelectorAll:()=>[]},
    fetch:async(input,init)=>{calls.push({input,init});return {ok:true};}};
  box.window=box;box.parent=box;vm.runInNewContext(script,box);
  await box.fetch('/assistant/device-index');
  assert.equal(box.JilianDataMode.mode,'live');
  assert.equal(calls[0].init.headers.get('X-Jilian-Data-Mode'),'live');
  assert.equal(replaced[0],'http://127.0.0.1:8890/assistant-ui/?mode=live');
});
test('live mode marks same-origin API reads without forwarding the marker externally',async()=>{
  const calls=[],href='http://127.0.0.1:8890/assistant-ui/?mode=live';
  const box={URL,URLSearchParams,Headers,
    location:{href,search:'?mode=live',origin:'http://127.0.0.1:8890'},
    document:{addEventListener(){},documentElement:{dataset:{}},querySelectorAll:()=>[]},
    fetch:async(input,init)=>{calls.push({input,init});return {ok:true};}};
  box.window=box;box.parent=box;
  vm.runInNewContext(script,box);
  await box.fetch('/assistant/device-index');
  await box.fetch('https://example.com/assistant/device-index');
  assert.equal(calls[0].init.headers.get('X-Jilian-Data-Mode'),'live');
  assert.equal(calls[1].init,undefined);
});

test('saved Trackunit research links without a mode stay in formal data',async()=>{
  const calls=[],href='http://127.0.0.1:8890/assistant-ui/?research=old&dataset=old#trackunit-asset=old';
  const box={URL,URLSearchParams,Headers,
    location:{href,search:'?research=old&dataset=old',hash:'#trackunit-asset=old',origin:'http://127.0.0.1:8890'},
    document:{addEventListener(){},documentElement:{dataset:{}},querySelectorAll:()=>[]},
    fetch:async(input,init)=>{calls.push({input,init});return {ok:true};}};
  box.window=box;box.parent=box;
  vm.runInNewContext(script,box);
  await box.fetch('/assistant/device-index');
  assert.equal(box.JilianDataMode.mode,'live');
  assert.equal(calls[0].init.headers.get('X-Jilian-Data-Mode'),'live');
});

test('clicking the already selected mode keeps the current machine and analysis link',()=>{
  const navigations=[],href='http://127.0.0.1:8890/assistant-ui/?research=abc&dataset=old#trackunit-asset=asset';
  const box={URL,URLSearchParams,location:{href,search:'?research=abc&dataset=old',hash:'#trackunit-asset=asset',
      assign:url=>navigations.push(url)},document:{addEventListener(){},documentElement:{dataset:{}},querySelectorAll:()=>[]}};
  box.window=box;box.parent=box;vm.runInNewContext(script,box);
  box.JilianDataMode.switchTo('live');
  assert.deepEqual(navigations,[]);
  box.JilianDataMode.switchTo('demo');
  assert.deepEqual(navigations,[],'retired demo mode cannot replace the current machine');
});
