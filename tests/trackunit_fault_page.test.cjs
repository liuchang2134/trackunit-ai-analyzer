const {test}=require('node:test');
const assert=require('node:assert/strict');
const page=require('../extension/trackunit-fault-page.js');

const asset='00000000-0000-0000-0000-000004760361';

test('only the Trackunit asset Events page is eligible',()=>{
  assert.equal(page.assetFromUrl(`https://new.manager.trackunit.com/assets/${asset}/events`),asset);
  assert.equal(page.assetFromUrl(`https://new.manager.trackunit.com/assets/${asset}/status`),null);
  assert.equal(page.assetFromUrl(`https://attacker.example/assets/${asset}/events`),null);
});

test('visible J1939 fault card preserves page provenance and displayed time',()=>{
  const value='Low Sep 12, 2026, 7:37 AM Machine Fault Joystick 1 Theta-Axis Position - Voltage Above Normal, Or Shorted To High Source Suggested Action See manual SA 160 SPN 2664 FMI 3 Fault Code';
  assert.deepEqual(page.parseCardText(value,'Sep 12, 2026, 7:37 AM'),{
    code:'SPN 2664 / FMI 3',spn:2664,fmi:3,sa:160,
    description:'Joystick 1 Theta-Axis Position - Voltage Above Normal, Or Shorted To High Source',
    severity:'Low',displayed_at:'Sep 12, 2026, 7:37 AM',
  });
});

test('service reminders are classified separately from machine faults',()=>{
  const service=page.parseServiceCardText('Critical Jul 24, 2026 Overdue Service Test Plan - Wheel Loaders Operating hours 100 h 368 h overdue');
  assert.equal(service.kind,'overdue');
  assert.equal(service.plan,'Test Plan - Wheel Loaders');
  assert.equal(service.target_hours,100);
  assert.equal(service.hours_offset,368);
});
test('a service card or generic text is not promoted to a machine fault',()=>{
  assert.equal(page.parseCardText('Low Service maintenance due SA 160 SPN 444 FMI 1'),null);
  assert.equal(page.parseCardText('Machine Fault'),null);
});

test('capture reads rendered fault cards only and reports limited coverage',()=>{
  const previous={location:global.location,window:global.window,document:global.document,
    getComputedStyle:global.getComputedStyle};
  const card=(heading,text,visible=true)=>({
    innerText:text,querySelector:selector=>selector==='h2'?{textContent:heading}:
      selector==='time[datetime]'?{getAttribute:()=> 'Sep 12, 2026, 7:37 AM'}:null,
    getClientRects:()=>visible?[{}]:[],
  });
  try{
    global.location={href:`https://new.manager.trackunit.com/assets/${asset}/events`};
    global.window={};global.window.top=global.window;
    global.document={querySelectorAll:()=>[
      card('Overdue Service','Critical Overdue Service Test Plan - Wheel Loaders Operating hours 100 h 368 h overdue'),
      card('Machine Fault','Low Sep 12, 2026 Machine Fault Joystick voltage high SA 160 SPN 2664 FMI 3'),
      card('Machine Fault','Low Machine Fault Hidden voltage high SA 160 SPN 444 FMI 1',false),
    ]};
    global.getComputedStyle=()=>({visibility:'visible'});
    const capture=page.capture();
    assert.equal(capture.asset_id,asset);
    assert.equal(capture.source,'trackunit_visible_events_page');
    assert.equal(capture.coverage,'rendered_active_events_only');
    assert.equal(capture.active_event_count,2);
    assert.equal(capture.services.length,1);
    assert.equal(capture.services[0].kind,'overdue');
    assert.equal(capture.capture_status,'visible_fault_cards');
    assert.equal(capture.faults.length,1);
    assert.equal(capture.faults[0].code,'SPN 2664 / FMI 3');
  } finally {Object.assign(global,previous);}
});


test('XC948U-style Events page separates three fault codes from two maintenance reminders',()=>{
  const previous={location:global.location,window:global.window,document:global.document,
    getComputedStyle:global.getComputedStyle};
  const card=(heading,text)=>({innerText:text,querySelector:selector=>selector==='h2'?{textContent:heading}:
    selector==='time[datetime]'?{getAttribute:()=> 'Sep 12, 2026, 7:37 AM'}:null,
    getClientRects:()=>[{}]});
  try{
    global.location={href:`https://new.manager.trackunit.com/assets/${asset}/events`};
    global.window={};global.window.top=global.window;
    global.document={querySelectorAll:()=>[
      card('Overdue Service','Critical Overdue Service Test Plan - Wheel Loaders Operating hours 100 h 368 h overdue'),
      card('Upcoming service','Low Upcoming service Test Plan - Wheel Loaders Operating hours 500 h 32 h remaining'),
      card('Machine Fault','Low Machine Fault - Joystick 1 Theta-Axis Position Suggested Action SA 160 SPN 2664 FMI 3 Fault Code'),
      card('Machine Fault','Low Machine Fault - Battery Potential Suggested Action SA 160 SPN 444 FMI 1 Fault Code'),
      card('Machine Fault','Low Machine Fault - Battery Potential Suggested Action SA 163 SPN 444 FMI 1 Fault Code'),
    ]};
    global.getComputedStyle=()=>({visibility:'visible'});
    const result=page.capture();
    assert.equal(result.active_event_count,5);
    assert.equal(result.faults.length,3);
    assert.equal(result.services.length,2);
    assert.deepEqual(result.faults.map(item=>[item.sa,item.spn,item.fmi]),[[160,2664,3],[160,444,1],[163,444,1]]);
  }finally{Object.assign(global,previous);}
});
