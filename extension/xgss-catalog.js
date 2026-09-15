/* Read only rendered XGSS catalog labels and visible table cells. Never read storage,
 * cookies, scripts, application state, request data, input values or session URLs. */
var XGSSCatalog = (() => {
  const origin = 'https://xgss.xcmg.com';
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  function isXGSS(value) {
    try { const u = new URL(value); return u.protocol === 'https:' && u.hostname === 'xgss.xcmg.com' && !u.port && !u.username && !u.password; }
    catch { return false; }
  }
  const aliases = {
    name: ['名称','零件名称','物料名称','零件描述','品名','name','partname','description','partdescription'],
    part_number: ['物料编码','物料编号','零件编码','零件编号','零件号','件号','partnumber','partno','materialcode','materialnumber'],
    figure_ref: ['序号','图号','图示号','位置号','item','itemno','pos','position','ref','no'],
    quantity: ['数量','用量','quantity','qty']
  };
  const headerKey = value => clean(value).toLowerCase().replace(/[\s.：:_#()（）-]/g, '');
  function parse(snapshot) {
    const text = clean(snapshot.text), vins = [...new Set([...text.matchAll(/(?:PIN\s*\/\s*VIN|VIN|PIN|车架号|整机编号)\s*[:：]\s*([A-Z0-9]{8,32})(?![A-Z0-9])/gi)].map(m => m[1].toUpperCase()))];
    const model = text.match(/(?:机型|设备型号|Model)\s*[:：]\s*([A-Z][A-Z0-9.-]{1,39})/i)?.[1] || null;
    const configurations = [...new Set(text.match(/XE55U\.00(?:VIII|VII|III|VI|IV|IX|II|V|X|I)(?![A-Z])/g) || [])];
    const items = [], seen = new Set(); let recognized = false, skipped = 0;
    for (const table of snapshot.tables || []) {
      const columns = {};
      table.headers.forEach((h, index) => { for (const [field, values] of Object.entries(aliases)) if (values.includes(headerKey(h))) columns[field] = index; });
      if (columns.name === undefined || columns.part_number === undefined) continue;
      recognized = true;
      for (const row of table.rows) {
        const name = clean(row[columns.name]);
        const part_number = clean(row[columns.part_number]).replace(/\s*[+＋]\s*$/, '');
        if (!name || name.length > 240 || !/^[A-Z0-9][A-Z0-9._/-]{2,63}$/i.test(part_number) || !/\d/.test(part_number)) { skipped++; continue; }
        const figure_ref = columns.figure_ref === undefined ? null : clean(row[columns.figure_ref]).slice(0, 80) || null;
        const quantity = columns.quantity === undefined ? null : clean(row[columns.quantity]).slice(0, 40) || null;
        const key = JSON.stringify([part_number, name, figure_ref]);
        if (seen.has(key)) continue;
        seen.add(key); if (items.length < 200) items.push({name,part_number,figure_ref,quantity}); else skipped++;
      }
    }
    const assembly_path = [...new Set((snapshot.assembly_path || []).map(clean).filter(v => v && v.length <= 160))].slice(0, 12);
    const capture_status = vins.length > 1 ? 'ambiguous_vin' : !vins.length ? 'vin_missing' : !recognized ? 'unrecognized_table' : !items.length ? 'no_visible_rows' : 'visible_rows';
    return {schema_version:1,source:'xgss_visible_dom',source_url:origin+'/',vin:vins.length===1?vins[0]:null,
      model,configuration:configurations.length===1?configurations[0]:null,assembly_path,items,
      capture_status,visible_rows:items.length,skipped_rows:skipped,coverage:'visible_rows_only',
      warnings:['仅包含当前已显示的表格行；折叠分类、分页和未渲染行未读取。',
        ...(!assembly_path.length?['当前页面未识别到选中分类路径。']:[]),
        ...(skipped?['部分可见行缺少有效名称或料号，已跳过。']:[])]};
  }
  function collect(doc, view) {
    function visible(el) {
      if (!el || !el.getClientRects().length) return false;
      const style = view.getComputedStyle(el), r = el.getBoundingClientRect();
      if (style.visibility === 'hidden' || style.visibility === 'collapse' || style.display === 'none' || Number(style.opacity) === 0) return false;
      if (!(r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < view.innerHeight && r.left < view.innerWidth)) return false;
      for (let parent=el.parentElement;parent;parent=parent.parentElement) {
        const ps=view.getComputedStyle(parent),pr=parent.getBoundingClientRect();
        if (Number(ps.opacity)===0) return false;
        if (/(hidden|scroll|auto|clip)/.test(ps.overflowY || '') && (r.top>=pr.bottom || r.bottom<=pr.top)) return false;
        if (/(hidden|scroll|auto|clip)/.test(ps.overflowX || '') && (r.left>=pr.right || r.right<=pr.left)) return false;
      }
      return true;
    }
    const textOf = el => clean(typeof el.innerText === 'string' ? el.innerText : el.textContent);
    const tables = [], handled = new Set();
    for (const table of doc.querySelectorAll('table,[role="grid"],[role="table"],.el-table')) {
      if (!visible(table) || handled.has(table)) continue;
      // Element UI splits header/body into tables; process their rendered wrapper once.
      if (table.closest('.el-table') && table.closest('.el-table') !== table) continue;
      handled.add(table);
      let headers = [...table.querySelectorAll('thead th,[role="columnheader"]')].map(textOf);
      const rows = [];
      for (const row of table.querySelectorAll('tbody tr,[role="row"]')) {
        if (!visible(row)) continue;
        const cells = [...row.querySelectorAll('td,[role="cell"],[role="gridcell"]')];
        if (cells.length) rows.push(cells.map(cell => visible(cell) ? textOf(cell) : ''));
      }
      if (!headers.length) {
        const first = table.querySelector('tr');
        if (first && visible(first)) headers = [...first.querySelectorAll('th,td')].map(textOf);
      }
      if (headers.length) tables.push({headers,rows});
    }
    const assembly_path = [];
    const crumbs = [...doc.querySelectorAll('[aria-label="breadcrumb"] li,.el-breadcrumb__item,.ant-breadcrumb li')].filter(visible);
    crumbs.forEach(el => assembly_path.push(textOf(el)));
    const selected = [...doc.querySelectorAll('.el-tree-node.is-current,[role="treeitem"][aria-selected="true"],.ant-tree-treenode-selected')].find(visible);
    if (selected) {
      const chain=[]; let node=selected;
      while (node && chain.length < 12) {
        if (node.matches('.el-tree-node,[role="treeitem"],.ant-tree-treenode')) {
          const label=node.querySelector('.el-tree-node__label,.ant-tree-title') || node.querySelector(':scope > .el-tree-node__content') || node;
          if (visible(label)) chain.unshift(textOf(label).slice(0,160));
        }
        node=node.parentElement;
      }
      assembly_path.push(...chain);
    }
    // innerText reflects rendered text and excludes display:none/script nodes; never return
    // this body text. Only the explicitly labelled VIN/model/configuration leave the page.
    return parse({text:(doc.body?.innerText || '').slice(0,100000),tables,assembly_path});
  }
  function capture() {
    if (!isXGSS(location.href)) return null;
    return collect(document, window);
  }
  return {isXGSS,parse,collect,capture};
})();
if (typeof module !== 'undefined') module.exports = XGSSCatalog;
