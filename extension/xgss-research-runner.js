/* Bounded catalog navigation. The extension supplies the browser primitives;
   this controller never receives cookies, a session URL, or arbitrary code. */
(function(root) {
  // Chrome serializes each injected-script result separately. Object key order
  // is not evidence; array order, values and every capture field still are.
  const captureSignature=value=>JSON.stringify(value,(_key,item)=>
    item&&typeof item==='object'&&!Array.isArray(item)?
      Object.fromEntries(Object.keys(item).sort().map(key=>[key,item[key]])):item);
  async function run({vin,terms,maxPages=6},io) {
    if (!/^[A-Z0-9]{8,32}$/.test(vin) || !Array.isArray(terms) || !terms.length) throw new Error('缺少设备或部件检索词。');
    const limit=Math.min(8,Math.max(1,maxPages)), visited=new Set(), saved=new Set();
    const maxPolls=40,pollIntervalMs=350;
    const requestedTerms=[...new Set(terms)], matchedTerms=new Set();
    const normalize=value=>String(value).trim().toLocaleLowerCase();
    let exploreRoot=true;
    const result={pages:0,selected:[],unresolved:[],status:'completed',
      coverage:'captured_visible_content_only',matched_terms:[],unmatched_terms:[...requestedTerms],tree_scrolls:0,root_expansions:0};
    const recordMatches=target=>{
      // Production targets carry the adapter's exact matches. Older adapters or
      // fixtures may omit them; only an actual label/term match is a fallback.
      const matches=Array.isArray(target.matches)?target.matches:requestedTerms.filter(term=>
        normalize(target.label).includes(normalize(term)) || normalize(term).includes(normalize(target.label)));
      for(const term of requestedTerms) if(matches.some(match=>normalize(match)===normalize(term))) matchedTerms.add(term);
      result.matched_terms=requestedTerms.filter(term=>matchedTerms.has(term));
      result.unmatched_terms=requestedTerms.filter(term=>!matchedTerms.has(term));
    };
    const assertActive=()=>{if(io.cancelled()) throw new Error('资料收集已停止或设备已切换。');};
    const inspect=async()=>{
      assertActive();const state=await io.inspect(terms);assertActive();
      // iView updates the selected category before the table. A same-VIN
      // loading state is expected during this transition, but is never evidence.
      if(!['ready','loading'].includes(state?.status) || state.vin!==vin) throw new Error('无法确认同一 VIN 的 XGSS 页面。');
      return state;
    };
    const waitUntilReady=async state=>{
      for(let poll=0;state.status==='loading' && poll<maxPolls;poll++) {
        await io.wait(pollIntervalMs);state=await inspect();
        if(state.status==='loading' && (poll+1)%4===0) io.progress('正在等待图册内容更新…');
      }
      return state;
    };
    const signature=state=>captureSignature(state.capture);
    // Path/title and drawing can update before the table response. Neither is
    // evidence that the rendered parts rows or manual content has changed.
    const contentSignature=state=>captureSignature({items:state.capture?.items||[],manual_sections:state.capture?.manual_sections||[]});
    const rowSignature=state=>captureSignature(state.capture?.items||[]);
    const confirmedCategory=state=>state.category_confirmed===true&&
      typeof state.category_label==='string'&&normalize(state.category_label).length>0;
    const settledSignature=state=>captureSignature([state.capture,state.diagram_ref||null]);
    const settleSameCategory=async(seed,eligible=()=>true)=>{
      const category=normalize(seed.category_label);
      const path=captureSignature(seed.capture?.assembly_path);
      let current=seed,previous=settledSignature(seed),stable=0;
      for(let poll=0;poll<maxPolls;poll++){
        assertActive();await io.wait(pollIntervalMs);current=await inspect();
        if((poll+1)%4===0)io.progress('正在等待图册内容更新…');
        if(current.status==='loading'){previous=null;stable=0;continue;}
        if(!confirmedCategory(current)||normalize(current.category_label)!==category||
          captureSignature(current.capture?.assembly_path)!==path)
          throw new Error('图册分类已切换，请重新读取当前分类。');
        const snapshot=settledSignature(current);
        stable=snapshot===previous?stable+1:0;previous=snapshot;
        if(current.capture&&stable>=2&&eligible(current))return current;
      }
      throw new Error('本分类资料仍在更新，请稍后重新读取。');
    };
    const save=async(initial,eligible=()=>true)=>{
      let current=initial;
      // A changed snapshot restarts the whole text+image transaction, never
      // grafts a newer diagram onto old rows, and never retries persistence.
      for(let attempt=0;attempt<3;attempt++){
        if(!current.capture||saved.has(signature(current)))return {saved:false,state:current};
        assertActive();
        try{
          await io.save(current.capture,{category_label:current.category_label,
            category_confirmed:current.category_confirmed});
        }catch(error){
          assertActive();
          if(error?.code!=='capture_changed'||attempt===2||!confirmedCategory(current))throw error;
          io.progress('本页资料正在更新，正在重新核对文字与图示…');
          current=await settleSameCategory(current,eligible);continue;
        }
        assertActive();saved.add(signature(current));result.pages++;
        io.progress(`已提取 ${result.pages} 页资料`);return {saved:true,state:current};
      }
    };
    let state=await waitUntilReady(await inspect());
    if(state.status==='loading') {
      result.unresolved.push('初始图册');result.status='no_sources';return result;
    }
    if(state.capture&&confirmedCategory(state))state=await settleSameCategory(state);
    state=(await save(state)).state;
    for(let step=0;step<12 && result.pages<limit;step++) {
      const target=(state.targets||[]).find(t=>!visited.has(t.label));
      if(!target) {
        if(exploreRoot&&!result.selected.length&&result.root_expansions<2&&typeof io.expandRoot==='function') {
          const previousTree=state.tree_signature;
          assertActive();const expansion=await io.expandRoot(vin);assertActive();
          if(expansion?.status==='expanded') {
            result.root_expansions++;io.progress('展开整机分类，继续查找相关部件');
            let treeChanged=false;
            for(let poll=0;poll<maxPolls;poll++) {
              assertActive();await io.wait(pollIntervalMs);state=await inspect();
              if(state.status==='ready' && typeof previousTree==='string' &&
                typeof state.tree_signature==='string' && state.tree_signature!==previousTree) {
                treeChanged=true;break;
              }
              if((poll+1)%4===0)io.progress('正在等待整机分类展开…');
            }
            if(!treeChanged){
              result.unresolved.push('整机分类未完成展开');
              io.progress('整机分类未完成展开，已保留当前资料');break;
            }
            // Expanding a directory is not a term match or a new source page.
            continue;
          }
          if(!['end','target_missing'].includes(expansion?.status))throw new Error('无法确认同一 VIN 的 XGSS 分类目录。');
          exploreRoot=false;
        }
        if(typeof io.scrollTree!=='function' || result.tree_scrolls>=4) break;
        assertActive();const movement=await io.scrollTree(vin);assertActive();
        if(movement?.status==='end') break;
        if(movement?.status!=='scrolled') throw new Error('无法确认同一 VIN 的 XGSS 分类目录。');
        result.tree_scrolls++;io.progress('继续查看分类目录');
        await io.wait(pollIntervalMs);state=await waitUntilReady(await inspect());
        if(state.status==='loading') {result.unresolved.push('分类目录');break;}
        // Tree scrolling reveals labels, not a new catalog source. Only a
        // subsequent category selection can cause another capture to be saved.
        continue;
      }
      visited.add(target.label);assertActive();
      if(state.category_confirmed===true&&normalize(state.category_label)===normalize(target.label)&&saved.has(signature(state))){
        recordMatches(target);continue;
      }
      const before=signature(state),beforeContent=contentSignature(state),beforeRows=rowSignature(state),
        selected=await io.select(target.label,vin);assertActive();
      if(selected?.status!=='selected') {result.unresolved.push(target.label);continue;}
      result.selected.push(target.label);io.progress(`查找 ${target.label}`);
      // A changed, stable snapshot is required. An unchanged old table must not
      // be reported as the newly selected assembly's evidence.
      const eligible=current=>{
        const categoryMatches=current.category_label===undefined ||
          normalize(current.category_label)===normalize(target.label)&&
          (current.category_confirmed===true||!(current.capture?.items||[]).length);
        const contentChanged=(current.capture?.items||[]).length?
          rowSignature(current)!==beforeRows:contentSignature(current)!==beforeContent;
        return signature(current)!==before&&current.capture&&categoryMatches&&contentChanged;
      };
      let previous=null,stable=0,changed=false;
      for(let poll=0;poll<maxPolls;poll++) {
        await io.wait(pollIntervalMs);state=await inspect();
        if((poll+1)%4===0) io.progress('正在等待图册内容更新…');
        if(state.status==='loading') {previous=null;stable=0;continue;}
        const settled=settledSignature(state);
        stable=settled===previous?stable+1:0;previous=settled;
        if(eligible(state)&&stable>=2) {changed=true;break;}
      }
      if(changed){const persisted=await save(state,eligible);state=persisted.state;if(persisted.saved)recordMatches(target);}
      else result.unresolved.push(target.label);
      // Do not click another category while the previous request is still in
      // flight: its late response could otherwise be attributed to that category.
      if(!changed || state.status==='loading') break;
    }
    if(!result.pages) result.status='no_sources';
    else if(result.unresolved.length || result.pages>=limit || result.unmatched_terms.length || !result.selected.length || result.tree_scrolls>=4) result.status='partial';
    return result;
  }
  root.XGSSResearchRunner={run,captureSignature};
  if(typeof module!=='undefined')module.exports={run,captureSignature};
})(globalThis);
