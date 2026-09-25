const {test}=require('node:test');
const assert=require('node:assert/strict');
const page=require('../extension/trackunit-fault-page.js');

const asset='00000000-0000-0000-0000-000004760361';

test('history log retains resolved transmission text without manufacturing fault numbers',()=>{
  const row=page.parseLogRow(['Time','Type','System','SPN','FMI','Status'],
    ['June 29, 2026, 9:06 AM','Machine Fault','Transmission','Manufacturer assignable SPN','Abnormal Update Rate','RESOLVED']);
  assert.equal(row.status,'CLOSED');
  assert.equal(row.description,'Transmission / Manufacturer assignable SPN / Abnormal Update Rate');
  assert.equal(row.code,null);assert.equal(row.spn,null);assert.equal(row.fmi,null);assert.equal(row.sa,null);
  assert.equal(row.displayed_at,'June 29, 2026, 9:06 AM');
  assert.equal(row.page_event_id,null);
});

test('history log only reads explicit numbers in matching cells and rejects service rows',()=>{
  const headers=['Time','Type','Description','SPN','FMI','SA','Status'];
  const cells=['Sep 24, 2026','Machine Fault','Communication update rate','639','9','160','ACTIVE'];
  const row=page.parseLogRow(headers,cells,'event-25');
  assert.equal(row.code,'SPN 639 / FMI 9');assert.equal(row.sa,160);assert.equal(row.page_event_id,'event-25');
  assert.equal(row.status,'OPEN');
  assert.equal(page.parseLogRow(headers,[...cells.slice(0,6),'unrecognised']),null);
  assert.equal(page.parseLogRow(headers,cells.map((value,index)=>index===1?'Overdue Service':value)),null);
  assert.equal(page.parseLogRow(headers,cells.slice(1)),null);
});

test('capture includes visible historical rows and preserves their source URL without reading hidden rows',()=>{
  const previous={location:global.location,window:global.window,document:global.document,getComputedStyle:global.getComputedStyle};
  const headers=['Time','Type','System','SPN','FMI','Status'];
  const row=(visible,id)=>({getClientRects:()=>visible?[{}]:[],getAttribute:()=>id,
    querySelectorAll:()=>['June 29, 2026, 9:06 AM','Machine Fault','Transmission','Manufacturer assignable SPN','Abnormal Update Rate','RESOLVED'].map(innerText=>({innerText}))});
  const table={getClientRects:()=>[{}],querySelectorAll:selector=>selector.startsWith('thead')?headers.map(innerText=>({innerText})):[row(true,'shown'),row(false,'hidden')]};
  try{
    global.location={href:`https://new.manager.trackunit.com/assets/${asset}/events`};global.window={};global.window.top=global.window;
    global.document={querySelectorAll:selector=>selector.startsWith('table')?[table]:[]};global.getComputedStyle=()=>({visibility:'visible'});
    const capture=page.capture();
    assert.equal(capture.faults.length,1);assert.equal(capture.faults[0].page_event_id,'shown');
    assert.equal(capture.faults[0].status,'CLOSED');assert.equal(capture.active_event_count,0);
    assert.equal(capture.source_url,global.location.href);assert.equal(capture.coverage,'rendered_events_only');
  }finally{Object.assign(global,previous);}
});

test('three equal historical rows without source IDs remain three observations and table headers are excluded',()=>{
  const previous={location:global.location,window:global.window,document:global.document,getComputedStyle:global.getComputedStyle};
  const headers=['Time','Type','System','SPN','FMI','Status'];
  const values=['June 29, 2026, 9:06 AM','Machine Fault','Transmission','Manufacturer assignable SPN','Abnormal Update Rate','RESOLVED'];
  const row=(cells,id=null)=>({getClientRects:()=>[{}],getAttribute:()=>id,querySelectorAll:()=>cells.map(innerText=>({innerText}))});
  // Native and ARIA header rows can appear in a generic row query. Neither is
  // a fault: one has no data cells and the other contains column-label text.
  const rows=[row([]),row(headers),row(values),row(values),row(values)];
  const table={getClientRects:()=>[{}],querySelectorAll:selector=>selector.startsWith('thead')?headers.map(innerText=>({innerText})):rows};
  try{
    global.location={href:`https://new.manager.trackunit.com/assets/${asset}/events`};global.window={};global.window.top=global.window;
    global.document={querySelectorAll:selector=>selector.startsWith('table')?[table]:[]};global.getComputedStyle=()=>({visibility:'visible'});
    const capture=page.capture();
    assert.equal(capture.faults.length,3);
    assert.ok(capture.faults.every(fault=>fault.page_event_id===null&&fault.status==='CLOSED'));
    assert.ok(capture.faults.every(fault=>fault.spn===null&&fault.fmi===null));
  }finally{Object.assign(global,previous);}
});

test('historical rows deduplicate only when Trackunit supplies an equal actual event ID',()=>{
  const previous={location:global.location,window:global.window,document:global.document,getComputedStyle:global.getComputedStyle};
  const headers=['Time','Type','System','SPN','FMI','Status'];
  const values=['June 29, 2026, 9:06 AM','Machine Fault','Transmission','Manufacturer assignable SPN','Abnormal Update Rate','RESOLVED'];
  const row=id=>({getClientRects:()=>[{}],getAttribute:()=>id,querySelectorAll:()=>values.map(innerText=>({innerText}))});
  const table={getClientRects:()=>[{}],querySelectorAll:selector=>selector.startsWith('thead')?headers.map(innerText=>({innerText})):[row('source-event-1'),row('source-event-1'),row('source-event-2')]};
  try{
    global.location={href:`https://new.manager.trackunit.com/assets/${asset}/events`};global.window={};global.window.top=global.window;
    global.document={querySelectorAll:selector=>selector.startsWith('table')?[table]:[]};global.getComputedStyle=()=>({visibility:'visible'});
    const capture=page.capture();
    assert.deepEqual(capture.faults.map(fault=>fault.page_event_id),['source-event-1','source-event-2']);
  }finally{Object.assign(global,previous);}
});

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
    global.document={querySelectorAll:selector=>selector.startsWith('table')?[]:[
      card('Overdue Service','Critical Overdue Service Test Plan - Wheel Loaders Operating hours 100 h 368 h overdue'),
      card('Machine Fault','Low Sep 12, 2026 Machine Fault Joystick voltage high SA 160 SPN 2664 FMI 3'),
      card('Machine Fault','Low Machine Fault Hidden voltage high SA 160 SPN 444 FMI 1',false),
    ]};
    global.getComputedStyle=()=>({visibility:'visible'});
    const capture=page.capture();
    assert.equal(capture.asset_id,asset);
    assert.equal(capture.source,'trackunit_visible_events_page');
    assert.equal(capture.coverage,'rendered_events_only');
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
    global.document={querySelectorAll:selector=>selector.startsWith('table')?[]:[
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
