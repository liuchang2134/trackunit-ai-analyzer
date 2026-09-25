/* Local, user-entered reference prices. No pricing API or automatic quotation. */
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.JilianPartEstimates = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const CURRENCIES = Object.freeze(['USD', 'CNY', 'EUR', 'GBP', 'CAD', 'AUD']);
  const MAX_UNIT_MINOR = 99999999999;
  const PREFIX = 'jilian.part-estimates.v1:';
  const EVIDENCE_LABELS = Object.freeze({inspection_only: '核查候选', historical_reference: '历史备库参考', conditional_candidate: '条件性备件'});
  const validCurrency = value => CURRENCIES.includes(value);
  function parseQuantity(value) {
    const text = String(value ?? '').trim();
    const number = Number(text);
    return /^\d+$/.test(text) && Number.isSafeInteger(number) && number >= 1 && number <= 9999 ?
      {ok: true, value: number} : {ok: false, error: '数量须为 1–9999 的整数。'};
  }
  function parseUnitPrice(value) {
    const text = String(value ?? '').trim();
    if (!/^\d+(?:\.\d{1,2})?$/.test(text)) return {ok: false, error: '请输入非负单价，最多两位小数。'};
    const [whole, fraction = ''] = text.split('.');
    if (whole.length > 12) return {ok: false, error: '单价超出可录入范围。'};
    const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
    return minor <= BigInt(MAX_UNIT_MINOR) ? {ok: true, minor: Number(minor)} :
      {ok: false, error: '单价不能超过 999,999,999.99。'};
  }
  function normalizeQuote(value, currency) {
    if (!value || typeof value !== 'object' || value.version !== 1 || value.origin !== 'user' ||
        !validCurrency(currency) || value.currency !== currency ||
        !Number.isSafeInteger(value.unitMinor) || value.unitMinor < 0 || value.unitMinor > MAX_UNIT_MINOR ||
        typeof value.quantity !== 'number' || !parseQuantity(value.quantity).ok ||
        typeof value.source !== 'string' || !value.source.trim() || value.source.length > 160 ||
        typeof value.updatedAt !== 'string' || !/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value.updatedAt) ||
        !Number.isFinite(Date.parse(value.updatedAt))) return null;
    return {version: 1, origin: 'user', currency, quantity: value.quantity, unitMinor: value.unitMinor,
      source: value.source.trim(), updatedAt: value.updatedAt};
  }
  function quoteFromInput(input, currency, updatedAt) {
    if (!validCurrency(currency)) return {ok: false, error: '请选择支持的币种。'};
    const quantity = parseQuantity(input.quantity), price = parseUnitPrice(input.unitPrice);
    if (!quantity.ok) return quantity;
    if (!price.ok) return price;
    if (typeof input.source !== 'string' || !input.source.trim() || input.source.length > 160)
      return {ok: false, error: '请填写价格来源（最多 160 字）。'};
    const quote = normalizeQuote({version: 1, origin: 'user', currency, quantity: quantity.value,
      unitMinor: price.minor, source: input.source, updatedAt}, currency);
    return quote ? {ok: true, quote} : {ok: false, error: '录入时间无效，未保存价格。'};
  }
  function summarize(values, currency) {
    if (!validCurrency(currency)) throw new Error('Unsupported currency');
    let total = 0n, quotedCount = 0;
    for (const value of values) {
      const quote = normalizeQuote(value, currency);
      if (!quote) continue;
      total += BigInt(quote.unitMinor) * BigInt(quote.quantity); quotedCount++;
    }
    const pendingCount = values.length - quotedCount;
    return {currency, quotedCount, pendingCount, totalMinor: quotedCount ? total.toString() : null,
      state: !values.length ? 'empty' : !quotedCount ? 'pending' : pendingCount ? 'partial' : 'all'};
  }
  function formatMinor(minor, currency) {
    if (!validCurrency(currency) || !/^\d+$/.test(String(minor))) return '待询价';
    const value = BigInt(minor), whole = (value / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return `${currency} ${whole}.${(value % 100n).toString().padStart(2, '0')}`;
  }
  const bounded = (value, max) => typeof value === 'string' && value.length <= max;
  function identityKey(context) {
    if (!context || !bounded(context.researchId, 128) || !context.researchId ||
        !bounded(context.machineId, 200) || !context.machineId || !bounded(context.scope, 64) || !context.scope ||
        !bounded(context.vin || '', 64) || !bounded(context.datasetId || '', 128)) return null;
    return JSON.stringify([context.machineId, context.datasetId || '', context.researchId, context.scope, context.vin || '']);
  }
  function partKey(part) {
    return part && bounded(part.part_number, 100) && part.part_number.trim() &&
      bounded(part.capture_id || '', 128) ? JSON.stringify([part.part_number.trim(), part.capture_id || '']) : null;
  }
  function storageKey(context, part, currency) {
    const identity = identityKey(context), item = partKey(part);
    return identity && item && validCurrency(currency) ? PREFIX + JSON.stringify([identity, item, currency]) : null;
  }
  function normalizeParts(parts) {
    const seen = new Set(), result = [];
    for (const part of Array.isArray(parts) ? parts : []) {
      const key = partKey(part); if (!key || seen.has(key)) continue;
      seen.add(key); result.push({name: String(part.name || '配件').slice(0, 200), part_number: part.part_number.trim(),
        capture_id: part.capture_id || '', figure_ref: String(part.figure_ref || '').slice(0, 80),
        evidence_level: Object.hasOwn(EVIDENCE_LABELS, part.evidence_level) ? part.evidence_level : ''});
    }
    return result;
  }
  function mount(container, options) {
    if (!container || !container.ownerDocument) throw new TypeError('A DOM container is required');
    const doc = container.ownerDocument, context = {...options}, parts = normalizeParts(options?.parts);
    const memory = new Map(), base = identityKey(context), currencyKey = base ? PREFIX + base + ':currency' : null;
    let storage = null, storageFailed = !base, destroyed = false, currency = 'USD', opened = false, bindings = [];
    try { storage = base ? doc.defaultView?.localStorage || null : null; } catch { storageFailed = true; }
    if (!storage) storageFailed = true;
    function read(key) {
      if (!key) return null;
      if (memory.has(key)) return memory.get(key);
      if (!storage) return null;
      try { const value = storage.getItem(key); memory.set(key, value); return value; }
      catch { storageFailed = true; storage = null; return null; }
    }
    function write(key, value) {
      if (!key) { storageFailed = true; return; }
      memory.set(key, value);
      if (!storage) { storageFailed = true; return; }
      try { value === null ? storage.removeItem(key) : storage.setItem(key, value); }
      catch { storageFailed = true; storage = null; }
    }
    const savedCurrency = read(currencyKey); if (validCurrency(savedCurrency)) currency = savedCurrency;
    function keyFor(part) { return storageKey(context, part, currency) || JSON.stringify([partKey(part), currency]); }
    function quoteFor(part) {
      const raw = read(keyFor(part));
      try { return normalizeQuote(JSON.parse(raw), currency); } catch { return null; }
    }
    function el(tag, text, className) {
      const node = doc.createElement(tag); if (text !== undefined) node.textContent = String(text);
      if (className) node.className = className; return node;
    }
    function bind(node, event, handler) { node.addEventListener(event, handler); bindings.push([node, event, handler]); }
    function unbind() { for (const [node, event, handler] of bindings) node.removeEventListener(event, handler); bindings = []; }
    function field(label, value, {type = 'text', step, min, max, mode, placeholder, maxLength} = {}) {
      const wrap = el('label', undefined, 'part-estimate-field'), caption = el('span', label), input = el('input');
      input.type = type; input.value = value; input.setAttribute('aria-label', label);
      if (step) input.step = step; if (min !== undefined) input.min = min; if (max !== undefined) input.max = max;
      if (mode) input.inputMode = mode; if (placeholder) input.placeholder = placeholder; if (maxLength) input.maxLength = maxLength;
      wrap.append(caption, input); return {wrap, input};
    }
    function render() {
      if (destroyed) return; unbind();
      const section = el('section', undefined, 'part-estimates'); section.setAttribute('aria-label', '配件参考估价');
      const summary = summarize(parts.map(quoteFor), currency), heading = el('div', undefined, 'part-estimate-heading');
      const title = el('strong', '配件参考估价');
      const amount = summary.state === 'all' ? `合计 ${formatMinor(summary.totalMinor, currency)}` :
        summary.state === 'partial' ? `已录金额 ${formatMinor(summary.totalMinor, currency)} · ${summary.pendingCount} 项待询价` :
        summary.state === 'pending' ? `${summary.pendingCount} 项待询价` : '暂无可估价配件';
      heading.append(title, el('span', amount, 'part-estimate-total')); section.append(heading);
      const provenance = el('p', '用户参考价 · 非 XGSS 报价，不代表全部需要更换。', 'part-estimate-note'); section.append(provenance);
      if (parts.length) {
        const details = el('details'); details.open = opened;
        details.append(el('summary', '录入参考价格'));
        bind(details, 'toggle', () => { opened = details.open; });
        const currencyLabel = el('label', undefined, 'part-estimate-currency'), select = el('select');
        select.setAttribute('aria-label', '估价币种');
        for (const code of CURRENCIES) { const option = el('option', code); option.value = code; select.append(option); }
        select.value = currency; currencyLabel.append(el('span', '币种'), select, el('span', '按币种分别保存，不自动换算。', 'part-estimate-note'));
        details.append(currencyLabel);
        bind(select, 'change', () => { if (!validCurrency(select.value)) return; currency = select.value; write(currencyKey, currency); render(); });
        for (const part of parts) {
          const quote = quoteFor(part), row = el('div', undefined, 'part-estimate-row');
          row.append(el('strong', part.name));
          if (part.evidence_level) row.append(el('p', EVIDENCE_LABELS[part.evidence_level], 'part-estimate-note'));
          row.append(el('span', part.part_number + (part.figure_ref ? ` · 图序 ${part.figure_ref}` : ''), 'part-estimate-part'));
          const state = quote ? `用户录入 · ${new Date(quote.updatedAt).toLocaleString()} · 来源：${quote.source}` : '待询价';
          row.append(el('p', state, 'part-estimate-note'));
          const form = el('div', undefined, 'part-estimate-fields');
          const quantity = field('数量', String(quote?.quantity || 1), {type: 'number', step: '1', min: 1, max: 9999, mode: 'numeric'});
          const unitPrice = field(`单价（${currency}）`, quote ? `${Math.floor(quote.unitMinor / 100)}.${String(quote.unitMinor % 100).padStart(2, '0')}` : '',
            {type: 'text', mode: 'decimal', placeholder: '待询价', maxLength: 16});
          const source = field('价格来源', quote?.source || '', {placeholder: '供应商报价、采购记录等', maxLength: 160});
          source.wrap.className += ' part-estimate-source';
          const save = el('button', '保存参考价'), clear = el('button', '清除价格'); save.type = clear.type = 'button';
          clear.hidden = !quote; const error = el('p', '', 'part-estimate-error'); error.setAttribute('role', 'status');
          form.append(quantity.wrap, unitPrice.wrap, source.wrap, save, clear); row.append(form, error); details.append(row);
          bind(save, 'click', () => {
            const result = quoteFromInput({quantity: quantity.input.value, unitPrice: unitPrice.input.value, source: source.input.value}, currency, new Date().toISOString());
            if (!result.ok) { error.textContent = result.error; return; }
            write(keyFor(part), JSON.stringify(result.quote)); render();
          });
          bind(clear, 'click', () => { write(keyFor(part), null); render(); });
        }
        section.append(details);
      }
      if (storageFailed) section.append(el('p', '本次价格仅保存在当前页面。', 'part-estimate-note'));
      container.replaceChildren(section);
    }
    render();
    return {refresh: render, destroy() { destroyed = true; unbind(); container.replaceChildren(); }};
  }
  return {mount, CURRENCIES, parseQuantity, parseUnitPrice, normalizeQuote, quoteFromInput, summarize,
    formatMinor, identityKey, partKey, storageKey, normalizeParts};
});
