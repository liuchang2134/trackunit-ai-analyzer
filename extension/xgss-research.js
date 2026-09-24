/* Rendered XGSS research adapter. No storage, cookie access or hidden state.
   Navigation uses existing tree labels; diagrams come only from a visible,
   same-origin image2d embed and are rasterized locally. */
var XGSSResearch = (() => {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const normal = value => clean(value).toLocaleLowerCase();
  function rank(labels, terms) {
    const keywords = [...new Set((terms || []).filter(x => typeof x === 'string' && x.trim().length >= 2 && x.length <= 40).map(normal))];
    return labels.map((label, index) => ({label, index,
      matches: keywords.filter(term => normal(label).includes(term) || term.includes(normal(label)))}))
      .filter(row => row.label.length >= 2 && row.matches.length)
      .sort((a,b) => b.matches.length-a.matches.length || a.index-b.index);
  }
  function visible(el, view) {
    if (!el?.getClientRects().length) return false;
    const style = view.getComputedStyle(el), rect = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    if (rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= view.innerHeight || rect.left >= view.innerWidth) return false;
    for (let p=el.parentElement; p; p=p.parentElement) {
      const ps=view.getComputedStyle(p), pr=p.getBoundingClientRect();
      if (Number(ps.opacity)===0 || ps.visibility==='hidden' || ps.display==='none') return false;
      if (/(hidden|scroll|auto|clip)/.test(ps.overflowY || '') && (rect.top>=pr.bottom || rect.bottom<=pr.top)) return false;
    }
    return true;
  }
  function treeLabels(doc, view) {
    return [...doc.querySelectorAll('.el-tree-node__label,.ant-tree-title,[role="treeitem"] > [data-label],.ivu-tree-title[title]')]
      .filter(el => visible(el,view) && clean(el.innerText).length > 1 && clean(el.innerText).length <= 160);
  }
  function manualSections(doc, view) {
    const sections=[], seen=new Set();
    // Only named document regions or explicitly labelled repair headings count.
    // The site navigation and whole body never become a supposed manual excerpt.
    const add = (title, value) => {
      const text=clean(value);
      if (!title || text.length<10 || text.length>10000 || seen.has(text) || sections.length>=12) return;
      if (sections.reduce((n,s)=>n+s.text.length,0)+text.length>30000) return;
      sections.push({title:clean(title).slice(0,180),text}); seen.add(text);
    };
    for (const region of doc.querySelectorAll('article,[role="document"],.manual-content,.document-content')) {
      if (!visible(region,view)) continue;
      const heading=region.querySelector('h1,h2,h3,[role="heading"]');
      if (heading && /故障|排查|维修|保养|troubleshoot|maintenance|repair/i.test(heading.innerText || '')) add(heading.innerText,region.innerText);
    }
    if (!sections.length) for (const heading of doc.querySelectorAll('h1,h2,h3,h4,[role="heading"]')) {
      if (!visible(heading,view) || !/故障基本信息|排查|维修|保养|troubleshoot|maintenance|repair/i.test(heading.innerText || '')) continue;
      const fragments=[];
      for (let sibling=heading.nextElementSibling, n=0; sibling && n<16; sibling=sibling.nextElementSibling,n++) {
        if (/^H[1-6]$/.test(sibling.tagName) || sibling.getAttribute('role')==='heading') break;
        if (visible(sibling,view) && !/^(SCRIPT|STYLE|INPUT|FORM|NAV)$/.test(sibling.tagName)) fragments.push(sibling.innerText || '');
      }
      add(heading.innerText,fragments.join('\n'));
    }
    return sections;
  }
  function inspect(terms=[], doc=document, view=window) {
    if (!XGSSCatalog.isXGSS(view.location.href)) return {status:'wrong_origin'};
    const catalog=XGSSCatalog.collect(doc,view);
    if (!catalog.vin || ['ambiguous_vin','vin_missing'].includes(catalog.capture_status)) return {status:catalog.capture_status};
    const labels=treeLabels(doc,view).map(el=>clean(el.innerText));
    // Root arrows can update immediately while their children arrive later.
    // Track visible directory labels independently of the unchanged parts table.
    const tree_signature=JSON.stringify(labels);
    // The tree selection changes before the asynchronous table response arrives.
    // Wait for the table's own heading to agree, otherwise rows get the wrong source.
    const selected=doc.querySelector('.ivu-tree-title-selected');
    const tableHeading=doc.querySelector('#printDiv img[title="转至上一级"]')?.previousElementSibling;
    if (selected && tableHeading && !clean(tableHeading.innerText).endsWith(clean(selected.innerText))) {
      return {status:'loading',vin:catalog.vin,tree_signature};
    }
    const manuals=manualSections(doc,view);
    const title=clean(doc.querySelector('h1,h2,[role="heading"]')?.innerText || doc.title || 'XGSS 官方资料').slice(0,200);
    return {status:'ready',vin:catalog.vin,tree_signature,can_expand_root:rootExpansion(doc,view).status==='expandable',targets:rank(labels,terms),
      capture:catalog.items.length || manuals.length ? {source:'xgss_rendered_page',source_url:'https://xgss.xcmg.com/',
        vin:catalog.vin,title,assembly_path:catalog.assembly_path,items:catalog.items,
        manual_sections:manuals,coverage:'rendered_content_only'} : null};
  }
  function illustrationContext(doc, view) {
    const embeds=[...doc.querySelectorAll('embed#svg')].filter(node=>visible(node,view));
    if(!embeds.length)return {issue:null};
    if(embeds.length!==1)return {issue:'本页存在多个图示，保留文字资料。'};
    const embed=embeds[0],raw=embed.getAttribute('src');
    const selected=clean(doc.querySelector('.ivu-tree-title-selected')?.innerText);
    const heading=clean(doc.querySelector('#printDiv img[title="转至上一级"]')?.previousElementSibling?.innerText);
    if(!selected || !heading || !heading.endsWith(selected))return {issue:'图示所属分类未确认，保留文字资料。'};
    try {
      const page=new URL(view.location.href),base=doc.baseURI || page.href;
      // embed.src includes the document's effective <base>; checking raw src
      // alone could otherwise reload a different image from another origin.
      if(typeof raw!=='string' || !raw || raw!==raw.trim() || /[?#]/.test(raw))throw new Error();
      const resolved=new URL(embed.src || raw,base),fromAttribute=new URL(raw,base);
      if(resolved.href!==fromAttribute.href || resolved.origin!==page.origin || resolved.protocol!=='https:' ||
        resolved.username || resolved.password || resolved.search || resolved.hash ||
        !/^\/api\/doc\/image2d\/[0-9]+\.svg$/.test(resolved.pathname) ||
        (raw!==resolved.pathname && raw!==resolved.href))throw new Error();
      return {embed,src:resolved.href,raw,selected,heading,document_ref:resolved.pathname.split('/').at(-1)};
    } catch (_) { return {issue:'图示来源未能核对，保留文字资料。'}; }
  }
  function cropIllustration(canvas, context, doc) {
    if(!context.getImageData)return canvas;
    const width=canvas.width,height=canvas.height,pixels=context.getImageData(0,0,width,height).data;
    let left=width,top=height,right=-1,bottom=-1;
    // Crop measured ink only. Never infer a part location or add a highlight.
    // The source canvas is bounded to 1600 px per side before this scan.
    for(let y=0;y<height;y++)for(let x=0;x<width;x++){
      const i=(y*width+x)*4;
      if(pixels[i+3]>16 && (pixels[i]<250||pixels[i+1]<250||pixels[i+2]<250)){
        left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);
      }
    }
    if(right<left)return canvas;
    left=Math.max(0,left-24);top=Math.max(0,top-24);
    right=Math.min(width-1,right+24);bottom=Math.min(height-1,bottom+24);
    if(left===0&&top===0&&right===width-1&&bottom===height-1)return canvas;
    const cropped=doc.createElement('canvas');cropped.width=right-left+1;cropped.height=bottom-top+1;
    const output=cropped.getContext('2d');if(!output)return canvas;
    output.fillStyle='#ffffff';output.fillRect(0,0,cropped.width,cropped.height);
    output.drawImage(canvas,left,top,cropped.width,cropped.height,0,0,cropped.width,cropped.height);
    return cropped;
  }
  function rasterizeIllustration(src, doc, view) {
    return new Promise(resolve=>{
      let picture,timer,settled=false;
      const finish=(data_url,issue)=>{
        if(settled)return;settled=true;view.clearTimeout(timer);
        if(picture){picture.onload=picture.onerror=null;if(!data_url)picture.removeAttribute?.('src');}
        resolve({data_url,issue});
      };
      try {
        picture=new view.Image();
        timer=view.setTimeout(()=>finish(null,'图示读取超时，保留文字资料。'),4500);
        picture.onerror=()=>finish(null,'图示读取失败，保留文字资料。');
        picture.onload=()=>{
          if(settled)return;
          try {
            const width=picture.naturalWidth,height=picture.naturalHeight;
            if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw new Error();
            const scale=1600/Math.max(width,height),canvas=doc.createElement('canvas');
            canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale));
            const context=canvas.getContext('2d');if(!context)throw new Error();
            context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);
            context.drawImage(picture,0,0,canvas.width,canvas.height);
            const output=cropIllustration(canvas,context,doc);
            const data=output.toDataURL('image/png'),match=/^data:image\/png;base64,([A-Za-z0-9+/]+={0,2})$/.exec(data);
            if(!match || match[1].length%4!==0)throw new Error();
            const bytes=match[1].length/4*3-(match[1].endsWith('==')?2:match[1].endsWith('=')?1:0);
            if(bytes>1500000){finish(null,'图示过大，保留文字资料。');return;}
            finish(data,null);
          } catch (_) { finish(null,'图示读取失败，保留文字资料。'); }
        };
        picture.src=src;
      } catch (_) { finish(null,'图示读取失败，保留文字资料。'); }
    });
  }
  async function captureWithIllustration(terms=[], doc=document, view=window) {
    const before=inspect(terms,doc,view);
    if(before.status!=='ready' || !before.capture)return before;
    const initial=illustrationContext(doc,view);
    if(!initial.embed)return initial.issue?{...before,illustration_issue:initial.issue}:before;
    const textFingerprint=JSON.stringify(before.capture);
    const image=await rasterizeIllustration(initial.src,doc,view);
    const after=inspect(terms,doc,view),current=illustrationContext(doc,view);
    if(after.status!=='ready' || after.vin!==before.vin || JSON.stringify(after.capture)!==textFingerprint ||
      current.embed!==initial.embed || current.src!==initial.src || current.raw!==initial.raw ||
      current.selected!==initial.selected || current.heading!==initial.heading){
      return {status:'loading',vin:after.vin,illustration_issue:'资料已变化，请重新读取当前分类。'};
    }
    if(!image.data_url)return {...before,illustration_issue:image.issue};
    return {...before,capture:{...before.capture,illustrations:[{
      title:(initial.selected+' · 图示').slice(0,200),document_ref:initial.document_ref,data_url:image.data_url
    }]}};
  }
  function select(label, vin, doc=document, view=window) {
    const current=inspect([],doc,view);
    if (current.status!=='ready' || current.vin!==vin) return {status:'vin_mismatch'};
    const targets=treeLabels(doc,view).filter(el=>clean(el.innerText)===label);
    if (targets.length!==1) return {status:targets.length?'ambiguous_target':'target_missing'};
    // A model can supply labels, never arbitrary selectors, scripts or URLs.
    targets[0].click();
    return {status:'selected',label};
  }
  function rootExpansion(doc,view) {
    const trees=[...doc.querySelectorAll('.tree.ivu-tree')].filter(el=>visible(el,view));
    if(trees.length!==1)return {status:trees.length?'ambiguous_target':'target_missing'};
    const tree=trees[0];
    // Observed iView markup has a vehicle root and, sometimes, one same-name
    // whole-machine child. Expand only this unambiguous two-level chain, never
    // an arbitrary unmatched assembly or a same-name title elsewhere on page.
    let level=[...tree.querySelectorAll('li')].filter(node=>{
      for(let parent=node.parentElement;parent&&parent!==tree;parent=parent.parentElement)
        if(parent.tagName==='LI')return false;
      return true;
    });
    let rootLabel=null;
    for(let depth=0;depth<2;depth++) {
      if(level.length!==1)return {status:'end'};
      const node=level[0],wrappers=[...node.querySelectorAll(':scope > .ivu-tree-title')].filter(el=>visible(el,view));
      if(wrappers.length!==1)return {status:'end'};
      // XGSS wraps its titled span in an untitled iView title span. Keep both
      // supported shapes scoped to this LI so a child title cannot stand in.
      const wrapper=wrappers[0],labels=[...(wrapper.hasAttribute('title')?[wrapper]:[]),
        ...wrapper.querySelectorAll('.ivu-tree-title[title]')]
        .filter(el=>el.closest('li')===node&&visible(el,view));
      if(labels.length!==1)return {status:'end'};
      const label=labels[0];
      if(clean(label.innerText).length<2)return {status:'end'};
      if(depth===0)rootLabel=clean(label.innerText);
      else if(clean(label.innerText)!==rootLabel){
        // The market-specific vehicle root and its unique .00 whole-machine
        // child have different visible names in the observed XC948 catalog.
        const parent=/^([A-Z]+\d+[A-Z0-9-]*)\s+(.+)$/i.exec(rootLabel);
        const child=/^([A-Z]+\d+[A-Z0-9-]*)\.00\s+(.+)$/i.exec(clean(label.innerText));
        if(!parent||!child||parent[1].toUpperCase()!==child[1].toUpperCase()||
          !(parent[2]===child[2]||parent[2].startsWith(child[2]+'-')))return {status:'end'};
      }
      const arrow=node.querySelector(':scope > .ivu-tree-arrow');
      if(!arrow||!visible(arrow,view)||!arrow.querySelector('.ivu-icon-ios-arrow-forward'))return {status:'end'};
      if(!arrow.classList.contains('ivu-tree-arrow-open'))return {status:'expandable',arrow,depth};
      level=[...node.querySelectorAll(':scope > ul.ivu-tree-children > li')];
    }
    return {status:'end'};
  }
  function expandRoot(vin,doc=document,view=window) {
    const current=inspect([],doc,view);
    if(current.status!=='ready'||current.vin!==vin)return {status:'vin_mismatch'};
    const candidate=rootExpansion(doc,view);
    if(candidate.status!=='expandable')return {status:candidate.status};
    candidate.arrow.click();return {status:'expanded',depth:candidate.depth};
  }
  function scrollTree(vin,doc=document,view=window) {
    const current=inspect([],doc,view);
    if(current.status!=='ready'||current.vin!==vin)return {status:'vin_mismatch'};
    // Observed XGSS iView tree; only this named directory region may be scrolled.
    const trees=[...doc.querySelectorAll('.tree.ivu-tree')].filter(el=>visible(el,view));
    if(trees.length!==1)return {status:trees.length?'ambiguous_target':'target_missing'};
    const tree=trees[0],before=tree.scrollTop,max=tree.scrollHeight-tree.clientHeight;
    if(before>=max-1)return {status:'end'};
    tree.scrollTop=Math.min(max,before+Math.max(1,Math.floor(tree.clientHeight*.75)));
    return {status:tree.scrollTop>before?'scrolled':'end'};
  }
  return {rank,visible,manualSections,inspect,captureWithIllustration,select,expandRoot,scrollTree};
})();
if (typeof module!=='undefined') module.exports=XGSSResearch;
