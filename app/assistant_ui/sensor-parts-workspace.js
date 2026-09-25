/* Explicit, sensor-scoped parts lookup. Never changes the homepage's active research. */
(() => {
  const root = typeof window === 'undefined' ? globalThis : window;
  const entries = new Map();
  const hash = value => /^[a-f0-9]{64}$/.test(value || '');
  const researchId = value => /^[a-f0-9]{32}$/.test(value || '');
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const button = (text, action) => {
    const item = node('button', text); item.type = 'button'; item.onclick = action; return item;
  };
  const stable = value => JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
  const aborted = () => new DOMException('Stopped', 'AbortError');
  const current = (entry, generation) => entry.generation === generation && !entry.controller?.signal.aborted &&
    entry.options.isCurrent() && entry.options.target.isConnected !== false;
  const check = (entry, generation) => { if (!current(entry, generation)) throw aborted(); };
  const identity = entry => ({machine_id:entry.machine.machine_id, dataset_id:entry.machine.dataset_id, vin:entry.machine.serial_number});
  const sameMachine = (entry, value) => value && value.machine_id === entry.machine.machine_id &&
    value.dataset_id === entry.machine.dataset_id && value.vin === entry.machine.serial_number;
  const faultBound = value => value.fault_event_id || value.source_report_id || value.manual_fault || value.manual_fault_reference ||
    value.engineering_fault || value.catalog_fault_code || value.fault_context?.trackunit_event || value.fault_context?.trackunit_page ||
    value.fault_context?.manual_fault || value.fault_context?.engineering_fault || value.fault_context?.manuals?.length;
  const validTerm = term => typeof term === 'string' && term.trim().length >= 2 && term.trim().length <= 40 && !/[<>\r\n]|https?:\/\//i.test(term);
  const uniqueTerms = values => [...new Set(values.filter(validTerm).map(term => term.trim()))];
  const termsKey = terms => stable([...terms].sort());
  function collectionTerms(entry) {
    if (entry.collectionTerms) return entry.collectionTerms;
    const seedTerms = uniqueTerms(entry.seed.search_terms);
    const planned = uniqueTerms(entry.record.plan.directions.flatMap(direction => Array.isArray(direction?.search_terms) ? direction.search_terms : []));
    // Preserve the selected risk's terms even when three AI directions fill all
    // twelve slots. Catalog/category synonyms use the remaining positions.
    return [...planned.filter(term => !seedTerms.includes(term)).slice(0,12-seedTerms.length),...seedTerms];
  }
  const retained = entry => {
    const message = entry.record?.pages?.length ? '已读取的图册资料仍保留。' :
      entry.record?.plan ? '已保留本项风险与检索方向，尚未读取到图册资料。' :
        entry.seed ? '已保留本项风险方向，尚未读取到图册资料。' : '尚未取得可用的风险或图册资料。';
    return message + (entry.resultRecord && !entry.complete ? '下方仍为上次候选结果。' : '');
  };

  function validateSeed(entry, seed) {
    if (!sameMachine(entry, seed) || seed.series_id !== entry.options.seriesId || seed.hypothesis_index !== entry.options.hypothesisIndex ||
      seed.symptom_source !== 'user_question' || typeof seed.symptom !== 'string' || !seed.symptom.trim() || seed.symptom.length > 3000 ||
      !Array.isArray(seed.search_terms) || !seed.search_terms.length || seed.search_terms.length > 12 || !seed.search_terms.every(validTerm))
      throw new Error('风险资料与当前设备或所选风险方向不一致，未开始查询。');
    if (!seed.hypothesis || stable(seed.hypothesis) !== stable(entry.options.hypothesis)) {
      const error = new Error('风险分析已更新，请重新打开故障预测后选择对应方向');
      error.kind = 'sensor_hypothesis_changed'; throw error;
    }
  }

  function validateRecord(entry, record, previous = null, analyzed = false) {
    if (!sameMachine(entry, record) || !researchId(record.research_id) || record.symptom_source !== 'user_question' ||
      record.symptom !== entry.seed.symptom.trim() || record.analysis_mode !== 'fault' || faultBound(record) ||
      !record.plan || !Array.isArray(record.plan.directions) || !Array.isArray(record.pages) ||
      !Number.isInteger(record.revision) || record.revision < 0 ||
      previous && (record.research_id !== previous.research_id || record.revision < previous.revision || stable(record.plan) !== stable(previous.plan)))
      throw new Error('返回资料与本次风险问题不一致，未载入。');
    if (analyzed && (record.revision !== previous.revision || record.analysis_revision !== record.revision || !record.advice ||
      !Array.isArray(record.advice.parts) || !Array.isArray(record.advice.inspection_targets || []) || record.advice.analysis_scope === 'historical'))
      throw new Error('配件分析与当前资料版本不一致，已保留图册供重试。');
  }

  function buildPanel(entry) {
    const target = entry.options.target; target.hidden = false; target.replaceChildren();
    target.className = 'sensor-parts-panel'; target.setAttribute('aria-label', '潜在故障配件');
    const status = node('p', '', 'sensor-parts-status'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const actions = node('div', '', 'sensor-parts-actions'), content = node('div', '', 'sensor-parts-content');
    target.append(node('h4', '潜在故障配件'), status, actions, content);
    entry.ui = {status, actions, content};
  }

  function retry(entry, text = '重试') {
    entry.ui.actions.replaceChildren(button(text, () => open(entry.options)));
  }

  function offerSourceRefresh(entry, text = '补充图册与图示') {
    entry.ui.actions.replaceChildren(button(text, () => {
      entry.complete = false; entry.collected = false; entry.forceRefresh = true;
      return open(entry.options);
    }));
  }

  function stop(entry) {
    const visible = entry.options.isCurrent() && entry.options.target.isConnected !== false;
    entry.generation++; entry.controller?.abort(); entry.controller = null; entry.promise = null;
    if (visible && entry.ui) { entry.ui.status.textContent = '已停止。' + retained(entry); retry(entry, '继续查询'); }
  }

  async function request(entry, generation, url, body, stream = false, method = 'POST') {
    check(entry, generation);
    const signal = entry.controller.signal;
    const response = await fetch(url, {method, headers:{'Content-Type':'application/json'}, signal,
      body:body === null ? undefined : JSON.stringify(body)});
    check(entry, generation);
    if (!response.ok) {
      const problem = await response.json().catch(() => ({})); check(entry, generation);
      const detail = problem.detail;
      const error = new Error(typeof detail === 'string' ? detail : detail?.message || problem.message || '请求未完成，请重试。');
      error.kind = detail?.kind || problem.kind; throw error;
    }
    if (!stream) { const result = await response.json(); check(entry, generation); return result; }
    if (!response.body?.getReader) throw new Error('未收到完整的资料响应，请重试。');
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '', result = null;
    const consume = block => {
      const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
      if (!data) return;
      const event = JSON.parse(data); check(entry, generation);
      if (event.type === 'error') { const error = new Error(event.message || '本次查询暂未完成。'); error.kind = event.kind; throw error; }
      if (event.type === 'cancelled') throw aborted();
      if (event.type === 'progress') entry.ui.status.textContent = String(event.message || '').slice(0,500);
      if (event.type === 'result') result = event.record;
    };
    try {
      while (true) {
        const chunk = await reader.read(); check(entry, generation);
        if (chunk.done) { buffer += decoder.decode(); break; }
        buffer += decoder.decode(chunk.value, {stream:true}).replace(/\r/g, '');
        if (buffer.length > 6000000) throw new Error('返回资料超出读取范围，请缩小方向后重试。');
        let end;
        while ((end = buffer.indexOf('\n\n')) >= 0) { const block = buffer.slice(0,end); buffer = buffer.slice(end+2); consume(block); }
      }
      if (buffer.trim()) consume(buffer);
    } finally { reader.releaseLock(); }
    if (!result) throw new Error('本次查询未产生完整结果，请重试。');
    return result;
  }

  function sourceParts(record) {
    const wholeMachine = /^(?:[A-Z]{1,8}\d[A-Z0-9._-]*\s*)?(?:(?:轮胎式|履带式|轮式|滑移|液压|电动|混合动力)?(?:装载机|挖掘机|压路机|推土机)|(?:全地面|越野轮胎|汽车|履带)?起重机|整机|整车|主机|(?:(?:wheel|wheeled|crawler|skid[- ]steer)\s+)?loader|(?:(?:hydraulic|crawler|wheeled)\s+)?excavator|(?:(?:truck|crawler|rough[- ]terrain|all[- ]terrain)\s+)?crane|whole machine|complete machine|complete vehicle)(?:\s*(?:整机|整车|总成))?$/i;
    return (record.evidence?.parts || []).filter(part => part && part.name && part.part_number &&
      !wholeMachine.test(String(part.name).trim()) && hash(part.capture_id) &&
      record.pages.some(page => page.capture_id === part.capture_id && page.content?.vin === record.vin));
  }

  function diagram(record, part) {
    if (!hash(part.capture_id)) return null;
    const page = record.pages.find(item => item.capture_id === part.capture_id && item.content?.vin === record.vin);
    const image = page?.illustrations?.find(item => hash(item.image_id));
    return image ? {url:`/assistant/xgss/research/${record.research_id}/images/${image.image_id}`, image, page} : null;
  }

  function coverage(entry, record = entry.record) {
    const direct = record?.direct_collection;
    if (!direct) return;
    const missing = [...(Array.isArray(direct.unmatched_terms) ? direct.unmatched_terms : []),
      ...(Array.isArray(direct.unresolved) ? direct.unresolved : [])].filter(value => typeof value === 'string');
    if (direct.status === 'partial' || missing.length) entry.ui.content.append(node('p',
      '图册读取范围有限。' + (missing.length ? '尚未完成：' + [...new Set(missing)].join('、') + '。' : ''), 'sensor-parts-coverage'));
  }

  function showParts(entry, record = entry.record) {
    const content = entry.ui.content; content.replaceChildren();
    const candidates = [...record.advice.parts.map(part => ({part, inspection:part.evidence_level === 'inspection_only' || part.status === 'inspection_only'})),
      ...(record.advice.inspection_targets || []).map(part => ({part, inspection:true}))];
    const evidence = sourceParts(record), groups = new Map(); let rejected = 0, missingImage = false;
    for (const candidate of candidates) {
      const part = candidate.part;
      if (!part || !evidence.some(source => source.source_id === part.source_id && source.capture_id === part.capture_id &&
        source.part_number === part.part_number && source.name === part.name) || !part.name || !part.part_number) { rejected++; continue; }
      const key = stable([part.part_number, part.name]);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(candidate);
    }
    entry.ui.status.textContent = groups.size ? `已找到 ${groups.size} 项潜在故障配件。` : '暂未匹配到可核对料号的潜在配件。';
    content.append(node('p', '以下按本项风险线索筛选；先核查适配及异常原因，再决定是否准备或更换。', 'sensor-series-limit'));
    const grid = node('div', '', 'sensor-parts-grid'); content.append(grid);
    for (const sources of groups.values()) {
      const {part} = sources[0], card = node('article', '', 'sensor-parts-card');
      card.append(node('h5', part.name), node('p', part.part_number, 'research-part-number'),
        node('small', sources.every(item => item.inspection) ? '待核查候选' : '有条件准备候选', 'sensor-parts-kind'));
      const illustrated = sources.map(item => ({part:item.part, value:diagram(record,item.part)})).find(item => item.value);
      if (illustrated) {
        const {url,image:metadata} = illustrated.value, figure = node('figure', '', 'sensor-parts-image');
        const sheetSet = /^sheets-/.test(metadata.document_ref || '');
        const sheetLabel = `${metadata.title} · 分类图册，请按页核对序号`;
        const link = node('a'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
        link.setAttribute('aria-label', sheetSet ? sheetLabel : `查看原图：${part.name}${illustrated.part.figure_ref ? '，图中序号 '+illustrated.part.figure_ref : ''}`);
        const image = node('img'); image.src = url; image.alt = sheetSet ? sheetLabel : `${part.name} · 同 VIN XGSS 原图`; image.loading = 'lazy';
        link.append(image);
        const caption = node('a', sheetSet ? sheetLabel : illustrated.part.figure_ref ? `图中序号 ${illustrated.part.figure_ref} · 查看原图` : '查看 XGSS 原图');
        caption.href = url; caption.target = '_blank'; caption.rel = 'noopener noreferrer';
        const imageStatus = node('p', '', 'sensor-parts-coverage'); imageStatus.setAttribute('role','status'); imageStatus.hidden = true;
        let imageAttempt = 0;
        const retryImage = button('重试图示', () => {
          retryImage.disabled = true; imageStatus.hidden = false; imageStatus.textContent = '正在重新加载该配件的原始图示…';
          link.hidden = false; image.src = url + '?retry=' + (++imageAttempt);
        }); retryImage.hidden = true;
        image.onerror = () => {
          link.hidden = true; imageStatus.hidden = false; imageStatus.textContent = '图示加载失败；配件料号与来源仍保留。';
          retryImage.hidden = false; retryImage.disabled = false;
          if (!entry.controller) offerSourceRefresh(entry);
        };
        image.onload = () => { link.hidden = false; imageStatus.hidden = true; imageStatus.textContent = ''; retryImage.hidden = true; retryImage.disabled = false; };
        figure.append(link,caption,imageStatus,retryImage); card.append(figure);
      } else { missingImage = true; card.append(node('p', '该配件对应分类尚未取得图示。', 'sensor-parts-coverage')); }
      const reasons = [...new Set(sources.map(item => item.part.reason).filter(Boolean))];
      for (const reason of reasons) card.append(node('p', reason));
      const basis = node('div', '', 'sensor-parts-basis'); basis.append(node('strong', '核查与准备条件'));
      const conditions = [...new Set(sources.map(item => item.part.preparation_condition || item.part.replacement_condition).filter(Boolean))];
      for (const condition of conditions.length ? conditions : ['尚缺明确准备条件，请先核对现场情况及适用手册。']) basis.append(node('p',condition));
      for (const source of sources) basis.append(node('p', `XGSS 来源：${source.part.assembly_path?.join(' / ') || source.part.page_title || '同 VIN 图册'}${source.part.figure_ref ? ' · 图中序号 '+source.part.figure_ref : ''}`));
      card.append(basis); grid.append(card);
    }
    if (!groups.size) content.append(node('p', '已读取的图册未形成可核对的候选；需要补充对应系统分类或现场检查依据。'));
    if (rejected) content.append(node('p', '部分候选的图册来源无法核对，未展示。', 'sensor-parts-coverage'));
    if (record.advice.summary) {
      const basis = node('details', '', 'sensor-parts-coverage');
      basis.append(node('summary', '查看 AI 匹配依据'),node('p',record.advice.summary)); content.append(basis);
    }
    coverage(entry,record); entry.ui.actions.replaceChildren();
    if (missingImage || !groups.size || record.direct_collection?.status === 'partial' ||
      record.direct_collection?.unmatched_terms?.length || record.direct_collection?.unresolved?.length) offerSourceRefresh(entry);
  }

  async function run(entry, generation) {
    let phase = '风险依据';
    try {
      if (!entry.seed) {
        entry.ui.status.textContent = '正在核对本项风险的连续资料…';
        const seed = await request(entry, generation, `/assistant/sensor-series/${entry.options.seriesId}/parts-handoff`,
          {machine_id:entry.machine.machine_id,dataset_id:entry.machine.dataset_id,hypothesis_index:entry.options.hypothesisIndex});
        validateSeed(entry,seed); entry.seed = seed;
      }
      if (!entry.record) {
        phase = '检索方向'; entry.ui.status.textContent = '正在生成本项风险的部件检索方向…';
        const planned = await request(entry,generation,'/assistant/xgss/research/plan',
          {...identity(entry),analysis_mode:'fault',symptom:entry.seed.symptom,symptom_source:'user_question'},true);
        validateRecord(entry,planned); entry.record = planned;
      }
      if (!entry.collected) {
        phase = '图册读取'; entry.ui.status.textContent = '正在读取同 VIN XGSS 图册与料号…';
        if (entry.refreshRevision) {
          // A prior direct-read commit may have succeeded before its response
          // was lost. Restore only this exact research, then retry the checked
          // sensor collection against its new revision; never read active/latest.
          const restored = await request(entry,generation,`/assistant/xgss/research/${entry.record.research_id}`,null,false,'GET');
          validateRecord(entry,restored,entry.record); entry.record = restored; entry.refreshRevision = false;
        }
        let terms = collectionTerms(entry), collected;
        while (true) {
          try {
            collected = await request(entry,generation,`/assistant/xgss/research/${entry.record.research_id}/collect-direct`,
              {expected_revision:entry.record.revision,terms,sensor_context:{series_id:entry.options.seriesId,hypothesis_index:entry.options.hypothesisIndex},
                ...(entry.forceRefresh ? {force_refresh:true} : {})},true);
            break;
          } catch (error) {
            check(entry,generation);
            if (error.kind !== 'direct_no_match' || entry.seedRecoveryTried) throw error;
            entry.seedRecoveryTried = true;
            const focused = uniqueTerms(entry.seed.search_terms);
            // Only one narrower attempt, and never repeat an identical query
            // merely with reordered words. Keep the same verified risk/record.
            if (termsKey(focused) === termsKey(terms)) throw error;
            terms = entry.collectionTerms = focused;
            entry.ui.status.textContent = '正在按本项风险的部件方向继续查找图册…';
          }
        }
        validateRecord(entry,collected,entry.record);
        if (!collected.direct_collection || !['completed','partial','cached'].includes(collected.direct_collection.status) ||
          collected.direct_collection.revision !== collected.revision) throw new Error('图册读取结果不完整，请重试。');
        entry.record = collected; entry.forceRefresh = false; entry.readFailed = false;
        if (!sourceParts(collected).length) {
          entry.ui.status.textContent = '暂未取得本项风险可核对的部件资料。';
          entry.ui.content.replaceChildren(node('p','已读取目录，但尚未匹配到具体配件；不会把整机目录当作候选。'));
          coverage(entry); offerSourceRefresh(entry,'继续读取图册'); return null;
        }
        entry.collected = true;
      }
      if (!entry.complete) {
        phase = '配件分析'; entry.ui.status.textContent = '正在筛选本项风险的潜在配件与准备条件…';
        const analyzed = await request(entry,generation,`/assistant/xgss/research/${entry.record.research_id}/analyze`,null,true);
        validateRecord(entry,analyzed,entry.record,true); entry.record = analyzed; entry.resultRecord = analyzed; entry.complete = true;
      }
      check(entry,generation); showParts(entry); return entry.record;
    } catch (error) {
      if (!current(entry,generation)) return null;
      if (['direct_sensor_context_invalid','direct_sensor_context_changed'].includes(error.kind)) {
        // Saved AI evidence can change independently of this open tab. A retry
        // must verify the current handoff again instead of repeating an old plan.
        entry.seed = null; entry.record = null; entry.resultRecord = null; entry.collected = false; entry.complete = false; entry.refreshRevision = false;
        entry.collectionTerms = null; entry.seedRecoveryTried = false; entry.forceRefresh = false; entry.readFailed = false;
        entry.ui.content.replaceChildren();
      }
      if (phase === '图册读取' && error.kind === 'direct_revision_changed') entry.refreshRevision = true;
      if (phase === '图册读取') entry.readFailed = true;
      if (error.kind === 'sensor_hypothesis_changed') {
        entry.ui.status.textContent = error.message; entry.ui.content.replaceChildren(); entry.ui.actions.replaceChildren(); return null;
      }
      entry.ui.status.textContent = error.name === 'AbortError' ? '已停止。' + retained(entry) :
        ['direct_sensor_context_invalid','direct_sensor_context_changed'].includes(error.kind) ? '风险分析依据已变化，请重试以重新核对本项风险。' :
          error.kind === 'direct_no_match' ? '尚未在该设备图册中匹配到本项风险的配件分类。' + retained(entry) :
            `${phase}暂未完成：${error.message || '请重试。'} ${retained(entry)}`;
      retry(entry,error.name === 'AbortError' ? '继续查询' : error.kind === 'direct_no_match' ? '重新查找图册' : '重试'); return null;
    } finally {
      if (entry.generation === generation) { entry.controller = null; entry.promise = null; }
    }
  }

  function open(options) {
    const machine = options?.machine, machineId = machine?.machine_id || machine?.id;
    if (!options?.target || typeof options.isCurrent !== 'function' || !options.isCurrent() || !machineId || !hash(machine.dataset_id) ||
      !/^[A-Z0-9]{8,32}$/.test(machine.serial_number || '') || !hash(options.seriesId) || !Number.isInteger(options.hypothesisIndex) ||
      options.hypothesisIndex < 0 || options.hypothesisIndex > 3 || options.analysisKey === undefined || options.analysisKey === null ||
      !options.hypothesis || typeof options.hypothesis !== 'object' || Array.isArray(options.hypothesis))
      return Promise.reject(new Error('风险资料或设备身份已变化，请重新选择当前风险方向。'));
    // Snapshot nested arrays as well as strings: the visible risk is the binding,
    // even if another render later reuses and edits the caller's object.
    const hypothesis = JSON.parse(stable(options.hypothesis));
    const key = stable([machineId,machine.dataset_id,machine.serial_number,options.seriesId,options.analysisKey,options.hypothesisIndex,hypothesis]);
    let entry = entries.get(key);
    if (entry?.promise && current(entry,entry.generation)) return entry.promise;
    if (!entry) { entry = {generation:0,seed:null,record:null,collected:false,complete:false}; entries.set(key,entry); }
    else if (entry.promise) stop(entry);
    entry.options = {...options,hypothesis}; entry.machine = {...machine,machine_id:machineId};
    buildPanel(entry);
    if (entry.complete) { showParts(entry); return Promise.resolve(entry.record); }
    if (entry.resultRecord) showParts(entry,entry.resultRecord);
    if (entry.readFailed) entry.forceRefresh = true;
    const generation = ++entry.generation; entry.controller = new AbortController();
    entry.ui.actions.replaceChildren(button('停止', () => stop(entry)));
    entry.promise = run(entry,generation); return entry.promise;
  }

  root.SensorPotentialParts = {open, cancelAll:() => { for (const entry of entries.values()) if (entry.promise) stop(entry); }};
})();
