const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const api=require('../extension/xgss-research.js');

test('research ranks existing tree labels using supplied component terms',()=>{
  const result=api.rank(['转台总成','冷却系统','散热器总成','液压系统'],['散热器','冷却','radiator']);
  assert.deepEqual(result.map(x=>x.label),['冷却系统','散热器总成']);
  assert.deepEqual(api.rank(['燃油箱'],['不存在的分类']),[]);
});

function fixture({vin='XUGTEST000000001',labels=['散热器总成'],manual=true}={}) {
  const view={location:{href:'https://xgss.xcmg.com/'},innerWidth:1000,innerHeight:800,
    getComputedStyle:()=>({display:'block',visibility:'visible',opacity:'1'})};
  const element=text=>({innerText:text,getClientRects:()=>[{}],getBoundingClientRect:()=>({width:100,height:30,top:0,left:0,right:100,bottom:30}),
    parentElement:null,click(){this.clicked=true;}});
  const nodes=labels.map(element);
  const heading=element('冷却系统维修');
  const article=element('冷却系统维修：停机冷却后按适用维修手册检查。'); article.querySelector=()=>heading;
  const doc={title:'XGSS 测试',querySelector:selector=>selector.startsWith('h1')?heading:null,querySelectorAll:selector=>selector.startsWith('.el-tree')?nodes:selector.startsWith('article')&&manual?[article]:[]};
  const catalog={vin,capture_status:vin?'no_visible_rows':'vin_missing',items:[],assembly_path:[]};
  const sandbox={module:{exports:{}},XGSSCatalog:{isXGSS:url=>url==='https://xgss.xcmg.com/',collect:()=>catalog},document:doc,window:view,URL};
  vm.runInNewContext(fs.readFileSync(require.resolve('../extension/xgss-research.js'),'utf8'),sandbox);
  return {api:sandbox.module.exports,doc,view,nodes,catalog,element};
}

test('manual-only page becomes a source, not an invented parts table',()=>{
  const f=fixture(), result=f.api.inspect(['冷却']);
  assert.equal(result.capture.manual_sections.length,1);
  assert.equal(result.capture.items.length,0);
  assert.equal(result.capture.source_url,'https://xgss.xcmg.com/');
  assert.equal('url' in result,false);
});

test('tree signature follows visible child labels independently of unchanged source capture',()=>{
  const f=fixture({labels:['越野轮胎起重机'],manual:false});
  const before=f.api.inspect(['空滤']);
  f.nodes.push(f.element('空滤器'));
  const after=f.api.inspect(['空滤']);
  assert.notEqual(after.tree_signature,before.tree_signature);
  assert.equal(before.capture,after.capture);
  assert.deepEqual(JSON.parse(after.tree_signature),['越野轮胎起重机','空滤器']);
  f.nodes.push({...f.element('隐藏分类'),getClientRects:()=>[]});
  assert.equal(f.api.inspect(['空滤']).tree_signature,after.tree_signature);
});

test('production tree changes cannot label the previous table as the new source',()=>{
  const f=fixture();const query=f.doc.querySelector;
  f.doc.querySelector=selector=>selector==='.ivu-tree-title-selected'?{innerText:'散热器安装组件'}:
    selector.startsWith('#printDiv')?{previousElementSibling:{innerText:'冷却系统'}}:query(selector);
  assert.equal(f.api.inspect(['散热器']).status,'loading');
});

test('missing VIN and missing documents cannot create a source',()=>{
  assert.equal(fixture({vin:null}).api.inspect().status,'vin_missing');
  assert.equal(fixture({manual:false}).api.inspect().capture,null);
});

test('selection is restricted to unique visible tree labels and same VIN',()=>{
  const f=fixture();
  assert.equal(f.api.select('散热器总成','OTHER').status,'vin_mismatch');
  assert.equal(f.api.select('加入购物车','XUGTEST000000001').status,'target_missing');
  assert.equal(f.api.select('散热器总成','XUGTEST000000001').status,'selected');
  assert.equal(f.nodes[0].clicked,true);
  const ambiguous=fixture({labels:['散热器总成','散热器总成']});
  assert.equal(ambiguous.api.select('散热器总成','XUGTEST000000001').status,'ambiguous_target');
  assert.equal(ambiguous.nodes.some(n=>n.clicked),false);
});

test('scrolling is limited to the matching VIN and observed directory region',()=>{
  const f=fixture(),query=f.doc.querySelectorAll;
  const tree={...f.nodes[0],scrollTop:0,scrollHeight:900,clientHeight:400,querySelectorAll:()=>[]};
  f.doc.querySelectorAll=selector=>selector==='.tree.ivu-tree'?[tree]:query(selector);
  assert.equal(f.api.scrollTree('OTHER').status,'vin_mismatch');assert.equal(tree.scrollTop,0);
  assert.equal(f.api.scrollTree('XUGTEST000000001').status,'scrolled');assert.equal(tree.scrollTop,300);
  assert.equal(f.api.scrollTree('XUGTEST000000001').status,'scrolled');assert.equal(tree.scrollTop,500);
  assert.equal(f.api.scrollTree('XUGTEST000000001').status,'end');
  f.doc.querySelectorAll=selector=>selector==='.tree.ivu-tree'?[tree,{...tree}]:query(selector);
  assert.equal(f.api.scrollTree('XUGTEST000000001').status,'ambiguous_target');
});

function collapsedRootFixture({rootOpen=true,childCount=1,directTitle=false}={}) {
  const f=fixture({labels:[],manual:false}),query=f.doc.querySelectorAll;
  const element=(tagName,className='',title=null)=>{
    const el={...f.element(''),tagName,children:[],title,
      classList:{contains:value=>className.split(' ').includes(value)},
      hasAttribute:name=>name==='title'&&el.title!==null,
      closest(selector){for(let p=this;p;p=p.parentElement)if(p.tagName===selector.toUpperCase())return p;return null;},
      append(child){child.parentElement=this;this.children.push(child);return child;}};
    el.querySelectorAll=selector=>{
      const descendants=parent=>parent.children.flatMap(child=>[child,...descendants(child)]);
      if(selector==='li')return descendants(el).filter(child=>child.tagName==='LI');
      if(selector===':scope > .ivu-tree-title')return el.children.filter(child=>child.classList.contains('ivu-tree-title'));
      if(selector===':scope > .ivu-tree-title[title]')return el.children.filter(child=>child.classList.contains('ivu-tree-title')&&child.hasAttribute('title'));
      if(selector===':scope > .ivu-tree-arrow')return el.children.filter(child=>child.classList.contains('ivu-tree-arrow'));
      if(selector===':scope > ul.ivu-tree-children > li')return el.children
        .filter(child=>child.tagName==='UL'&&child.classList.contains('ivu-tree-children'))
        .flatMap(child=>child.children.filter(item=>item.tagName==='LI'));
      if(selector==='.ivu-tree-title[title]')return descendants(el).filter(child=>child.classList.contains('ivu-tree-title')&&child.hasAttribute('title'));
      if(selector==='.ivu-icon-ios-arrow-forward')return descendants(el).filter(child=>child.classList.contains('ivu-icon-ios-arrow-forward'));
      throw new Error('Unsupported fixture selector: '+selector);
    };
    el.querySelector=selector=>el.querySelectorAll(selector)[0]||null;
    return el;
  };
  const tree=element('DIV','tree ivu-tree');
  const node=(parent,open)=>{
    const li=parent.append(element('LI')),arrow=li.append(element('SPAN','ivu-tree-arrow'));
    arrow.append(element('I','ivu-icon-ios-arrow-forward'));arrow.open=open;arrow.clicks=0;
    const contains=arrow.classList.contains;
    arrow.classList.contains=value=>value==='ivu-tree-arrow-open'?arrow.open:contains(value);
    arrow.click=()=>{arrow.clicks++;arrow.open=true;};
    li.arrow=arrow;
    li.wrapper=li.append(element('SPAN','ivu-tree-title',directTitle?'XUGTEST000000001/A.2':null));
    li.label=directTitle?li.wrapper:li.wrapper.append(element('SPAN','ivu-tree-title','XUGTEST000000001/A.2'));
    li.label.innerText='越野轮胎起重机';
    li.branch=li.append(element('UL','ivu-tree-children'));
    return li;
  };
  const root=node(tree,rootOpen);
  Array.from({length:childCount},()=>node(root.branch,false));
  f.nodes.push(root.label,...root.branch.children.map(child=>child.label));
  f.doc.querySelectorAll=selector=>selector==='.tree.ivu-tree'?[tree]:selector.startsWith('.el-tree')?tree.querySelectorAll('.ivu-tree-title[title]'):query(selector);
  return {...f,tree,root,treeElement:element};
}

test('single same-name whole-machine child expands by its arrow without ambiguous label selection',()=>{
  const f=collapsedRootFixture(),vin='XUGTEST000000001';
  assert.equal(f.api.select('越野轮胎起重机',vin).status,'ambiguous_target');
  assert.equal(f.api.expandRoot(vin).status,'expanded');
  assert.equal(f.root.arrow.clicks,0);assert.equal(f.root.branch.children[0].arrow.clicks,1);
  assert.equal(f.nodes.some(n=>n.clicked),false,'expansion never selects a duplicate label');
});

test('root exploration is bounded to a unique visible same-VIN chain of two levels',()=>{
  const f=collapsedRootFixture({rootOpen:false}),vin='XUGTEST000000001';
  assert.equal(f.api.expandRoot('OTHER').status,'vin_mismatch');assert.equal(f.root.arrow.clicks,0);
  assert.equal(f.api.expandRoot(vin).depth,0);assert.equal(f.api.expandRoot(vin).depth,1);
  assert.equal(f.api.expandRoot(vin).status,'end');
  const multiple=collapsedRootFixture({childCount:2});
  assert.equal(multiple.api.expandRoot(vin).status,'end');
  assert.equal(multiple.root.branch.children.some(n=>n.arrow.clicks),false);
  const hidden=collapsedRootFixture();hidden.root.branch.children[0].arrow.getClientRects=()=>[];
  assert.equal(hidden.api.expandRoot(vin).status,'end');
});

test('root-only bootstrap exposes an actionable directory without clicking or inventing parts',()=>{
  const f=collapsedRootFixture({rootOpen:false}),result=f.api.inspect(['空滤']);
  assert.equal(result.can_expand_root,true);assert.equal(result.capture,null);assert.equal(result.targets.length,0);
  assert.equal(f.root.arrow.clicks,0);assert.equal(f.root.branch.children[0].arrow.clicks,0);
  assert.equal(f.api.expandRoot('XUGTEST000000001').status,'expanded');
  assert.equal(f.api.inspect(['空滤']).can_expand_root,true,'same-name whole-machine child is still actionable');
  f.api.expandRoot('XUGTEST000000001');
  assert.equal(f.api.inspect(['空滤']).can_expand_root,false);
});

test('empty, hidden, ambiguous or unrelated singleton directories do not offer root bootstrap',()=>{
  assert.equal(fixture({labels:[],manual:false}).api.inspect(['空滤']).can_expand_root,false);
  const unrelated=collapsedRootFixture();unrelated.root.branch.children[0].label.innerText='发动机安装';
  assert.equal(unrelated.api.inspect(['空滤']).can_expand_root,false);
  assert.equal(unrelated.api.expandRoot('XUGTEST000000001').status,'end');
  assert.equal(unrelated.root.branch.children[0].arrow.clicks,0);
  const hidden=collapsedRootFixture();hidden.root.branch.children[0].label.getClientRects=()=>[];
  assert.equal(hidden.api.inspect(['空滤']).can_expand_root,false);
  const ambiguous=collapsedRootFixture(),query=ambiguous.doc.querySelectorAll;
  ambiguous.doc.querySelectorAll=selector=>selector==='.tree.ivu-tree'?[ambiguous.tree,{...ambiguous.tree}]:query(selector);
  assert.equal(ambiguous.api.inspect(['空滤']).can_expand_root,false);
  assert.equal(ambiguous.root.branch.children[0].arrow.clicks,0);
});

test('root bootstrap recognizes observed nested titles and legacy direct titles',()=>{
  for(const directTitle of [false,true]){
    const f=collapsedRootFixture({rootOpen:false,directTitle}),vin='XUGTEST000000001';
    assert.equal(Boolean(f.root.querySelector(':scope > .ivu-tree-title[title]')),directTitle);
    assert.equal(f.api.inspect(['空滤']).can_expand_root,true);
    assert.equal(f.root.arrow.clicks,0);
    assert.equal(f.api.expandRoot(vin).depth,0);
    assert.equal(f.api.expandRoot(vin).depth,1);
    assert.equal(f.root.arrow.clicks,1);assert.equal(f.root.branch.children[0].arrow.clicks,1);
  }
});

test('root bootstrap rejects ambiguous visible title wrappers and nested labels',()=>{
  for(const scenario of ['wrappers','nested-labels','direct-and-nested']){
    const f=collapsedRootFixture({rootOpen:false,directTitle:scenario==='direct-and-nested'});
    const duplicate=f.treeElement('SPAN','ivu-tree-title','XUGTEST000000001/A.2');duplicate.innerText='越野轮胎起重机';
    (scenario==='wrappers'?f.root:f.root.wrapper).append(duplicate);
    assert.equal(f.api.inspect(['空滤']).can_expand_root,false,scenario);
    assert.equal(f.api.expandRoot('XUGTEST000000001').status,'end',scenario);
    assert.equal(f.root.arrow.clicks,0,scenario);
    duplicate.getClientRects=()=>[];
    assert.equal(f.api.inspect(['空滤']).can_expand_root,true,'a hidden duplicate is not a visible candidate: '+scenario);
  }
});

test('root bootstrap never borrows a titled label from a child LI',()=>{
  for(const childInsideWrapper of [false,true]){
    const f=collapsedRootFixture({rootOpen:false});
    f.root.label.title=null;
    if(childInsideWrapper){
      f.root.children=f.root.children.filter(child=>child!==f.root.branch);
      f.root.wrapper.append(f.root.branch);
    }
    assert.equal(f.root.querySelectorAll('.ivu-tree-title[title]').length,1,'the child still has a titled label');
    assert.equal(f.api.inspect(['空滤']).can_expand_root,false);
    assert.equal(f.api.expandRoot('XUGTEST000000001').status,'end');
    assert.equal(f.root.arrow.clicks,0);assert.equal(f.root.branch.children[0].arrow.clicks,0);
  }
});

const PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1sAAAAASUVORK5CYII=';
function illustrationFixture({src='/api/doc/image2d/3944450.svg',width=3200,height=2000,dataURL=PNG}={}){
  const f=fixture(),query=f.doc.querySelector,queryAll=f.doc.querySelectorAll;
  f.catalog.items=[{name:'散热器',part_number:'TEST-001'}];f.catalog.assembly_path=['冷却系统'];
  f.selected={innerText:'冷却系统'};f.heading={innerText:'冷却系统'};
  f.embed={...f.element(''),getAttribute:name=>name==='src'?f.src:null,
    get src(){return new URL(f.src,f.doc.baseURI||f.view.location.href).href;}};
  f.src=src;f.embeds=[f.embed];
  f.doc.querySelector=selector=>selector==='.ivu-tree-title-selected'?f.selected:
    selector.startsWith('#printDiv')?{previousElementSibling:f.heading}:query(selector);
  f.doc.querySelectorAll=selector=>selector==='embed#svg'?f.embeds:queryAll(selector);
  f.images=[];f.loads=[];f.draws=[];f.timers=new Map();let timerId=0;
  f.view.Image=class {
    constructor(){this.naturalWidth=width;this.naturalHeight=height;f.images.push(this);}
    set src(value){f.loads.push(value);}
    removeAttribute(name){this.removed=name;}
  };
  f.view.setTimeout=(callback,ms)=>{const id=++timerId;f.timers.set(id,{callback,ms});return id;};
  f.view.clearTimeout=id=>f.timers.delete(id);
  const context={fillStyle:null,fillRect(...args){f.draws.push({type:'fill',color:this.fillStyle,args});},
    drawImage(_picture,...args){f.draws.push({type:'image',args});}};
  f.canvas={width:0,height:0,getContext:()=>context,toDataURL:type=>{assert.equal(type,'image/png');return dataURL;}};
  f.doc.createElement=tag=>{assert.equal(tag,'canvas');return f.canvas;};
  return f;
}

test('a visible same-origin diagram becomes a bounded white-background PNG attached to its text source',async()=>{
  const f=illustrationFixture(),pending=f.api.captureWithIllustration(['冷却']);
  assert.deepEqual(f.loads,['https://xgss.xcmg.com/api/doc/image2d/3944450.svg']);
  assert.equal(f.timers.values().next().value.ms,4500);
  f.images[0].onload();const result=await pending;
  assert.equal(result.status,'ready');assert.equal(result.capture.items[0].part_number,'TEST-001');
  assert.equal(result.capture.illustrations[0].document_ref,'3944450.svg');
  assert.equal(result.capture.illustrations[0].title,'冷却系统 · 图示');
  assert.equal(result.capture.illustrations[0].data_url,PNG);
  assert.equal(f.canvas.width,1600);assert.equal(f.canvas.height,1000);
  assert.deepEqual(f.draws,[{type:'fill',color:'#ffffff',args:[0,0,1600,1000]},{type:'image',args:[0,0,1600,1000]}]);
  assert.equal(f.timers.size,0);assert.equal(f.images[0].onload,null);assert.equal(f.images[0].onerror,null);
});

test('small natural SVG dimensions are rasterized at 1600 pixels for readable diagram labels',async()=>{
  const f=illustrationFixture({width:624,height:869}),pending=f.api.captureWithIllustration();
  f.images[0].onload();const result=await pending;
  assert.equal(result.capture.illustrations[0].data_url,PNG);
  assert.equal(f.canvas.width,1149);assert.equal(f.canvas.height,1600);
  assert.deepEqual(f.draws,[{type:'fill',color:'#ffffff',args:[0,0,1149,1600]},
    {type:'image',args:[0,0,1149,1600]}]);
});

test('diagram thumbnails crop only measured non-white pixels and keep a white margin',async()=>{
  const f=illustrationFixture({width:1600,height:1600}),context=f.canvas.getContext('2d');
  const pixels=new Uint8ClampedArray(1600*1600*4).fill(255);
  for(let y=35;y<=64;y++)for(let x=40;x<=59;x++){
    const index=(y*1600+x)*4;pixels[index]=pixels[index+1]=pixels[index+2]=20;
  }
  context.getImageData=()=>({data:pixels});
  const cropDraws=[],cropContext={fillStyle:null,
    fillRect(...args){cropDraws.push({type:'fill',color:this.fillStyle,args});},
    drawImage(source,...args){assert.equal(source,f.canvas);cropDraws.push({type:'image',args});}};
  const cropped={getContext:()=>cropContext,toDataURL:()=>PNG};let created=0;
  f.doc.createElement=()=>++created===1?f.canvas:cropped;
  const pending=f.api.captureWithIllustration();f.images[0].onload();const result=await pending;
  assert.equal(result.capture.illustrations[0].data_url,PNG);
  assert.equal(cropped.width,68);assert.equal(cropped.height,78);
  assert.deepEqual(cropDraws,[{type:'fill',color:'#ffffff',args:[0,0,68,78]},
    {type:'image',args:[16,11,68,78,0,0,68,78]}]);
});

test('diagram capture rejects unsafe sources before loading any image',async()=>{
  for(const src of ['https://other.example/api/doc/image2d/3944450.svg',
    'http://xgss.xcmg.com/api/doc/image2d/3944450.svg','https://user:secret@xgss.xcmg.com/api/doc/image2d/3944450.svg',
    '/api/doc/image2d/3944450.svg?token=private','/api/doc/image2d/3944450.svg#part','/api/doc/image2d/3944450.svg?',
    '/api/doc/image2d/3944450.svg#','/api/doc/image2d/private.svg','/api/doc/image2d/3944450.png',
    '/api/doc/image2d/../image2d/3944450.svg','data:image/svg+xml,test','//xgss.xcmg.com/api/doc/image2d/3944450.svg']){
    const f=illustrationFixture({src}),result=await f.api.captureWithIllustration(['冷却']);
    assert.equal(result.status,'ready',src);assert.equal(result.capture.illustrations,undefined,src);
    assert.equal(f.loads.length,0,src);assert.match(result.illustration_issue,/来源/);
  }
  const based=illustrationFixture();based.doc.baseURI='https://other.example/';
  const result=await based.api.captureWithIllustration();
  assert.equal(result.capture.illustrations,undefined);assert.equal(based.loads.length,0);
});

test('missing, hidden, ambiguous or unconfirmed diagrams leave the text capture unchanged',async()=>{
  for(const scenario of ['missing','hidden','ambiguous','unconfirmed']){
    const f=illustrationFixture();
    if(scenario==='missing')f.embeds=[];
    if(scenario==='hidden')f.embed.getClientRects=()=>[];
    if(scenario==='ambiguous')f.embeds=[f.embed,{...f.embed}];
    if(scenario==='unconfirmed')f.selected=null;
    const before=JSON.stringify(f.api.inspect().capture),result=await f.api.captureWithIllustration();
    assert.equal(JSON.stringify(result.capture),before,scenario);assert.equal(f.loads.length,0,scenario);
  }
});

test('image completion cannot attach a diagram after any source identity or table change',async()=>{
  for(const scenario of ['vin','category','heading','rows','manual','src','hidden','replaced']){
    const f=illustrationFixture(),pending=f.api.captureWithIllustration();
    if(scenario==='vin')f.catalog.vin='XUGOTHER00000002';
    if(scenario==='category'){f.selected.innerText=f.heading.innerText='水泵';f.catalog.assembly_path=['水泵'];}
    if(scenario==='heading')f.heading.innerText='另一分类';
    if(scenario==='rows')f.catalog.items[0].part_number='CHANGED-002';
    if(scenario==='manual'){
      const query=f.doc.querySelectorAll;
      f.doc.querySelectorAll=selector=>selector.startsWith('article')?[]:query(selector);
    }
    if(scenario==='src')f.src='/api/doc/image2d/9999999.svg';
    if(scenario==='hidden')f.embed.getClientRects=()=>[];
    if(scenario==='replaced')f.embeds=[{...f.embed}];
    f.images[0].onload();const result=await pending;
    assert.equal(result.status,'loading',scenario);assert.equal(result.capture,undefined,scenario);
    assert.match(result.illustration_issue,/资料已变化/);
  }
});

test('image load, strict-namespace SVG decode, canvas and size failures retain text while timeouts ignore a late onload',async()=>{
  for(const scenario of ['load','strict_namespace_svg','timeout','dimensions','canvas','context','oversized','invalid_png']){
    const f=illustrationFixture({width:scenario==='dimensions'?0:800,height:400,
      dataURL:scenario==='oversized'?'data:image/png;base64,'+'A'.repeat(2000004):scenario==='invalid_png'?'data:,':PNG});
    const before=JSON.stringify(f.api.inspect().capture),pending=f.api.captureWithIllustration();
    if(scenario==='canvas')f.canvas.toDataURL=()=>{throw new Error('tainted canvas');};
    if(scenario==='context')f.canvas.getContext=()=>null;
    if(scenario==='load'||scenario==='strict_namespace_svg')f.images[0].onerror({type:'error'});
    else if(scenario==='timeout'){
      const late=f.images[0].onload;f.timers.values().next().value.callback();late();
      assert.equal(f.draws.length,0);
    }else f.images[0].onload();
    const result=await pending;
    assert.equal(result.status,'ready',scenario);assert.equal(JSON.stringify(result.capture),before,scenario);
    assert.equal(result.capture.illustrations,undefined,scenario);assert.ok(result.illustration_issue,scenario);
    assert.equal(f.timers.size,0);assert.equal(f.images[0].onload,null);
  }
});


test('root bootstrap expands observed XC948 market root and same-model .00 vehicle only',()=>{
  for(const [parent,child,allowed] of [
    ['XC948 轮胎式装载机-美国','XC948.00 轮胎式装载机',true],
    ['XC948 轮胎式装载机-美国','XC918.00 轮胎式装载机',false],
    ['XC948 轮胎式装载机-美国','XC948.01 轮胎式装载机',false],
    ['XC948 轮胎式装载机-美国','XC948.00 发动机安装',false]]){
    const f=collapsedRootFixture();f.root.label.innerText=parent;
    f.root.branch.children[0].label.innerText=child;
    assert.equal(f.api.inspect(['电气系统']).can_expand_root,allowed,child);
    assert.equal(f.api.expandRoot('XUGTEST000000001').status,allowed?'expanded':'end',child);
    assert.equal(f.root.branch.children[0].arrow.clicks,allowed?1:0,child);
  }
});
