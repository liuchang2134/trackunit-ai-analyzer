/* Bounded catalog navigation. The extension supplies the browser primitives;
   this controller never receives cookies, a session URL, or arbitrary code. */
(function(root) {
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
    const signature=state=>JSON.stringify(state.capture);
    const save=async state=>{
      if(!state.capture || saved.has(signature(state)))return;
      assertActive(); await io.save(state.capture); assertActive();
      saved.add(signature(state));result.pages++;io.progress(`已提取 ${result.pages} 页资料`);
    };
    let state=await waitUntilReady(await inspect());
    if(state.status==='loading') {
      result.unresolved.push('初始图册');result.status='no_sources';return result;
    }
    await save(state);
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
      const before=signature(state), selected=await io.select(target.label,vin);assertActive();
      if(selected?.status!=='selected') {result.unresolved.push(target.label);continue;}
      result.selected.push(target.label);recordMatches(target);io.progress(`查找 ${target.label}`);
      // A changed, stable snapshot is required. An unchanged old table must not
      // be reported as the newly selected assembly's evidence.
      let previous=null,stable=0,changed=false;
      for(let poll=0;poll<maxPolls;poll++) {
        await io.wait(pollIntervalMs);state=await inspect();
        if((poll+1)%4===0) io.progress('正在等待图册内容更新…');
        if(state.status==='loading') {previous=null;stable=0;continue;}
        const current=signature(state);
        stable=current===previous?stable+1:0;previous=current;
        if(current!==before && state.capture && stable>=2) {changed=true;break;}
      }
      if(changed) await save(state);
      else result.unresolved.push(target.label);
      // Do not click another category while the previous request is still in
      // flight: its late response could otherwise be attributed to that category.
      if(state.status==='loading') break;
    }
    if(!result.pages) result.status='no_sources';
    else if(result.unresolved.length || result.pages>=limit || result.unmatched_terms.length || !result.selected.length || result.tree_scrolls>=4) result.status='partial';
    return result;
  }
  root.XGSSResearchRunner={run};
  if(typeof module!=='undefined')module.exports={run};
})(globalThis);
