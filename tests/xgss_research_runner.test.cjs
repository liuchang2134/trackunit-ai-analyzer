const {test}=require('node:test');
const assert=require('node:assert/strict');
const {run}=require('../extension/xgss-research-runner.js');
const VIN='XUGTEST000000001';
const state=(title,targets=[],labels=targets)=>({status:'ready',vin:VIN,tree_signature:JSON.stringify(labels),targets:targets.map(label=>({label})),capture:{title,vin:VIN,items:[]}});

test('collects changed settled source pages after term-driven navigation',async()=>{
  let page=state('整机',['冷却系统']),saved=[];
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>page,
    select:async()=>{page=state('冷却系统');return {status:'selected'};},wait:async()=>{},save:async p=>saved.push(p),progress:()=>{}});
  assert.equal(result.pages,2);assert.deepEqual(saved.map(p=>p.title),['整机','冷却系统']);
  assert.equal(result.coverage,'captured_visible_content_only');
  assert.deepEqual(result.matched_terms,['冷却']);assert.deepEqual(result.unmatched_terms,[]);
});

test('unchanged old table is never saved as a newly selected assembly',async()=>{
  const page=state('整机',['冷却系统']);let saved=0;
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>page,
    select:async()=>({status:'selected'}),wait:async()=>{},save:async()=>saved++,progress:()=>{}});
  assert.equal(saved,1);assert.equal(result.status,'partial');assert.deepEqual(result.unresolved,['冷却系统']);
});

test('device switching cancels collection before any further save',async()=>{
  let cancelled=false,saved=0;
  await assert.rejects(run({vin:VIN,terms:['冷却']},{cancelled:()=>cancelled,
    inspect:async()=>{cancelled=true;return state('整机');},wait:async()=>{},save:async()=>saved++,progress:()=>{}}),/停止|切换/);
  assert.equal(saved,0);
});

test('wrong-VIN page is rejected and per-run page cap is enforced',async()=>{
  await assert.rejects(run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>({...state('图册'),vin:'OTHER'})}),/VIN/);
  let selections=0;
  const result=await run({vin:VIN,terms:['冷却'],maxPages:1},{cancelled:()=>false,inspect:async()=>state('图册',['冷却']),
    select:async()=>{selections++;},save:async()=>{},progress:()=>{}});
  assert.equal(result.pages,1);assert.equal(selections,0);assert.equal(result.status,'partial');
});

test('same-VIN loading during category navigation waits for changed stable evidence',async()=>{
  let selected=false,polls=0;const saved=[];
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,
    inspect:async()=>!selected?state('整机',['冷却系统']):
      ++polls<=2?{status:'loading',vin:VIN}:state('冷却系统'),
    select:async()=>{selected=true;return {status:'selected'};},wait:async()=>{},
    save:async page=>saved.push(page.title),progress:()=>{}});
  assert.deepEqual(saved,['整机','冷却系统']);
  assert.equal(result.status,'completed');assert.equal(polls,5);
});

test('initial same-VIN loading is bounded and never saved as source evidence',async()=>{
  let reads=0,waits=0;const saved=[];
  const io={cancelled:()=>false,inspect:async()=>++reads<=2?{status:'loading',vin:VIN}:state('图册'),
    wait:async()=>{waits++;},save:async page=>saved.push(page.title),progress:()=>{}};
  const ready=await run({vin:VIN,terms:['冷却']},io);
  assert.equal(ready.pages,1);assert.deepEqual(saved,['图册']);assert.equal(waits,2);
  assert.equal(ready.status,'partial');assert.deepEqual(ready.matched_terms,[]);
  assert.deepEqual(ready.unmatched_terms,['冷却']);
  waits=0;saved.length=0;
  const timeout=await run({vin:VIN,terms:['冷却']},{...io,inspect:async()=>({status:'loading',vin:VIN})});
  assert.equal(timeout.status,'no_sources');assert.equal(timeout.pages,0);
  assert.equal(waits,40);assert.deepEqual(saved,[]);
});

test('category loading timeout returns partial evidence without another click or save',async()=>{
  let selected=false,clicks=0,waits=0;const saved=[];
  const result=await run({vin:VIN,terms:['冷却','水泵']},{cancelled:()=>false,
    inspect:async()=>selected?{status:'loading',vin:VIN}:state('整机',['冷却系统','水泵']),
    select:async()=>{selected=true;clicks++;return {status:'selected'};},
    wait:async()=>{waits++;},save:async page=>saved.push(page.title),progress:()=>{}});
  assert.equal(result.status,'partial');assert.deepEqual(result.unresolved,['冷却系统']);
  assert.deepEqual(saved,['整机']);assert.equal(clicks,1);assert.equal(waits,40);
});

test('loading never masks a changed VIN or cancellation',async()=>{
  let selected=false,polls=0;const saved=[];
  const io={cancelled:()=>false,
    inspect:async()=>selected?(polls++,{status:'loading',vin:'OTHER'}):state('整机',['冷却系统']),
    select:async()=>{selected=true;return {status:'selected'};},wait:async()=>{},
    save:async page=>saved.push(page.title),progress:()=>{}};
  await assert.rejects(run({vin:VIN,terms:['冷却']},io),/VIN/);
  assert.equal(polls,1);assert.deepEqual(saved,['整机']);
  let cancelled=false;saved.length=0;
  await assert.rejects(run({vin:VIN,terms:['冷却']},{...io,
    cancelled:()=>cancelled,inspect:async()=>({status:'loading',vin:VIN}),
    wait:async()=>{cancelled=true;}}),/停止|切换/);
  assert.deepEqual(saved,[]);
});

test('only selected targets contribute explicit matches and unsearched terms keep results partial',async()=>{
  let page={...state('整机'),targets:[{label:'冷却系统',matches:['冷却系统','radiator']}]};
  const result=await run({vin:VIN,terms:['冷却系统','Radiator','water pump']},{cancelled:()=>false,
    inspect:async()=>page,select:async()=>{page=state('冷却系统');return {status:'selected'};},
    wait:async()=>{},save:async()=>{},progress:()=>{}});
  assert.equal(result.pages,2);assert.equal(result.status,'partial');
  assert.equal(result.coverage,'captured_visible_content_only');
  assert.deepEqual(result.matched_terms,['冷却系统','Radiator']);
  assert.deepEqual(result.unmatched_terms,['water pump']);
});

test('a target merely found on the page or rejected by selection does not count as searched',async()=>{
  const page={...state('整机'),targets:[{label:'冷却系统',matches:['冷却']}]};
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>page,
    select:async()=>({status:'ambiguous_target'}),save:async()=>{},progress:()=>{}});
  assert.equal(result.status,'partial');assert.equal(result.pages,1);
  assert.deepEqual(result.selected,[]);assert.deepEqual(result.matched_terms,[]);
  assert.deepEqual(result.unmatched_terms,['冷却']);
});

test('bounded tree scrolling reveals later targets without duplicating the unchanged table',async()=>{
  let page=state('整机'),scrolls=0;const saved=[];
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>page,
    scrollTree:async vin=>{
      assert.equal(vin,VIN);scrolls++;
      if(scrolls===1) {page=state('整机',['冷却系统']);return {status:'scrolled'};}
      return {status:'end'};
    },select:async()=>{page=state('冷却系统');return {status:'selected'};},
    wait:async()=>{},save:async capture=>saved.push(capture.title),progress:()=>{}});
  assert.deepEqual(saved,['整机','冷却系统']);assert.equal(scrolls,2);
  assert.equal(result.tree_scrolls,1);assert.equal(result.status,'completed');
  assert.deepEqual(result.matched_terms,['冷却']);
});

test('four tree scrolls stop with partial coverage even when the known term was matched',async()=>{
  let page=state('整机',['冷却系统']),scrolls=0;const saved=[];
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,inspect:async()=>page,
    select:async()=>{page=state('冷却系统');return {status:'selected'};},
    scrollTree:async()=>{scrolls++;return {status:'scrolled'};},
    wait:async()=>{},save:async capture=>saved.push(capture.title),progress:()=>{}});
  assert.equal(scrolls,4);assert.equal(result.tree_scrolls,4);assert.equal(result.status,'partial');
  assert.deepEqual(result.unmatched_terms,[]);assert.deepEqual(saved,['整机','冷却系统']);
});

test('tree navigation stops immediately on a VIN rejection or cancellation',async()=>{
  let waits=0;
  const io={cancelled:()=>false,inspect:async()=>state('整机'),
    scrollTree:async()=>({status:'vin_mismatch'}),wait:async()=>{waits++;},
    save:async()=>{},progress:()=>{}};
  await assert.rejects(run({vin:VIN,terms:['冷却']},io),/VIN/);
  assert.equal(waits,0);
  let cancelled=false;
  await assert.rejects(run({vin:VIN,terms:['冷却']},{...io,cancelled:()=>cancelled,
    scrollTree:async()=>{cancelled=true;return {status:'scrolled'};}}),/停止|切换/);
  assert.equal(waits,0);
});

test('slow initial and category loads can exceed five seconds while progress stays active',async()=>{
  let selected=false,initialReads=0,categoryReads=0;const saved=[],progress=[],waits=[];
  const result=await run({vin:VIN,terms:['冷却']},{cancelled:()=>false,
    inspect:async()=>selected?
      (++categoryReads<=20?{status:'loading',vin:VIN}:state('冷却系统')):
      (++initialReads<=18?{status:'loading',vin:VIN}:state('整机',['冷却系统'])),
    select:async()=>{selected=true;return {status:'selected'};},
    wait:async ms=>waits.push(ms),save:async page=>saved.push(page.title),progress:message=>progress.push(message)});
  assert.equal(result.status,'completed');assert.deepEqual(saved,['整机','冷却系统']);
  assert.equal(initialReads,19);assert.equal(categoryReads,23);
  assert.ok(progress.filter(message=>message==='正在等待图册内容更新…').length>=9);
  assert.ok(waits.every(ms=>ms===350));
});

test('one bounded whole-machine expansion reveals terms without inventing a source or keyword match',async()=>{
  let page=state('整机'),expansions=0;const saved=[];
  const result=await run({vin:VIN,terms:['空滤']},{cancelled:()=>false,inspect:async()=>page,
    expandRoot:async vin=>{assert.equal(vin,VIN);expansions++;page=state('整机',['空滤器']);return {status:'expanded'};},
    select:async()=>{page=state('空滤器');return {status:'selected'};},wait:async()=>{},
    save:async capture=>saved.push(capture.title),progress:()=>{}});
  assert.equal(expansions,1);assert.equal(result.root_expansions,1);
  assert.deepEqual(saved,['整机','空滤器']);assert.deepEqual(result.selected,['空滤器']);
  assert.deepEqual(result.matched_terms,['空滤']);assert.equal(result.status,'completed');
});

test('unmatched root exploration stops after two expansions and remains partial',async()=>{
  let expansions=0,saves=0;
  const result=await run({vin:VIN,terms:['空滤']},{cancelled:()=>false,inspect:async()=>state('整机',[],Array(expansions+1).fill('整机')),
    expandRoot:async()=>{expansions++;return {status:'expanded'};},wait:async()=>{},save:async()=>saves++,progress:()=>{}});
  assert.equal(expansions,2);assert.equal(saves,1);assert.equal(result.status,'partial');
  assert.deepEqual(result.matched_terms,[]);assert.deepEqual(result.selected,[]);
});

test('slow root AJAX waits for actual tree labels even while the old parts table reports ready',async()=>{
  let expanded=false,polls=0,selected=false,expansions=0;const saved=[],progress=[];
  const result=await run({vin:VIN,terms:['空滤']},{cancelled:()=>false,
    inspect:async()=>selected?state('空滤器',[],['越野轮胎起重机','空滤器']):
      expanded&&++polls>=16?state('整机',['空滤器'],['越野轮胎起重机','空滤器']):state('整机',[],['越野轮胎起重机']),
    expandRoot:async()=>{expanded=true;expansions++;return {status:'expanded'};},
    select:async()=>{selected=true;return {status:'selected'};},
    wait:async ms=>assert.equal(ms,350),save:async page=>saved.push(page.title),progress:value=>progress.push(value)});
  assert.equal(expansions,1);assert.equal(polls,16);
  assert.deepEqual(saved,['整机','空滤器']);assert.equal(result.status,'completed');
  assert.deepEqual(result.matched_terms,['空滤']);
  assert.ok(progress.filter(value=>value==='正在等待整机分类展开…').length>=3);
});

test('unchanged root labels time out without another expansion, scroll, save, or invented match',async()=>{
  let waits=0,expansions=0,scrolls=0,saves=0;
  const result=await run({vin:VIN,terms:['空滤']},{cancelled:()=>false,
    inspect:async()=>state('整机',[],['越野轮胎起重机']),
    expandRoot:async()=>{expansions++;return {status:'expanded'};},
    scrollTree:async()=>{scrolls++;return {status:'end'};},wait:async()=>waits++,save:async()=>saves++,progress:()=>{}});
  assert.equal(waits,40);assert.equal(expansions,1);assert.equal(scrolls,0);assert.equal(saves,1);
  assert.equal(result.status,'partial');assert.deepEqual(result.unresolved,['整机分类未完成展开']);
  assert.deepEqual(result.matched_terms,[]);assert.deepEqual(result.selected,[]);
});

test('root wait checks cancellation and VIN before observing more labels or saving a page',async()=>{
  for(const mode of ['cancel','vin']) {
    let waits=0,saves=0,reads=0;
    const io={cancelled:()=>mode==='cancel'&&waits>=3,
      inspect:async()=>{reads++;return {...state('整机',[],['越野轮胎起重机']),vin:mode==='vin'&&waits>=3?'OTHER':VIN};},
      expandRoot:async()=>({status:'expanded'}),wait:async()=>waits++,save:async()=>saves++,progress:()=>{}};
    await assert.rejects(run({vin:VIN,terms:['空滤']},io),mode==='vin'?/VIN/:/停止|切换/);
    assert.equal(waits,3);assert.equal(saves,1);assert.ok(reads<=4);
  }
});

test('root expansion does not happen when a keyword target is already available',async()=>{
  let page=state('整机',['空滤器']),expansions=0;
  await run({vin:VIN,terms:['空滤']},{cancelled:()=>false,inspect:async()=>page,
    expandRoot:async()=>{expansions++;return {status:'expanded'};},
    select:async()=>{page=state('空滤器');return {status:'selected'};},wait:async()=>{},save:async()=>{},progress:()=>{}});
  assert.equal(expansions,0);
});

test('root expansion rejects VIN changes and cancellation before further reads or saves',async()=>{
  const io={cancelled:()=>false,inspect:async()=>state('整机'),wait:async()=>{},save:async()=>{},progress:()=>{}};
  await assert.rejects(run({vin:VIN,terms:['空滤']},{...io,expandRoot:async()=>({status:'vin_mismatch'})}),/VIN/);
  let cancelled=false;
  await assert.rejects(run({vin:VIN,terms:['空滤']},{...io,cancelled:()=>cancelled,
    expandRoot:async()=>{cancelled=true;return {status:'expanded'};}}),/停止|切换/);
});
