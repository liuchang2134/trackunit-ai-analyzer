/* Read only fault cards rendered on the current Trackunit asset Events page.
 * This is a partial page observation, never a replacement for the event API. */
var TrackunitFaultPage = (() => {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const assetFromUrl = value => {
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || !['new.manager.trackunit.com','manager.trackunit.com'].includes(url.hostname) ||
          url.username || url.password || url.port) return null;
      return url.pathname.match(/^\/assets\/([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\/events\/?$/i)?.[1].toLowerCase() || null;
    } catch { return null; }
  };
  function parseCardText(value, time = '') {
    const text = clean(value);
    if (!/\bMachine Fault\b/i.test(text)) return null;
    const tuple = text.match(/\bSA\s+(\d{1,3})\s+SPN\s+(\d{1,7})\s+FMI\s+(\d{1,2})\b/i);
    const oem = text.match(/\bFault Code\s*[:：]?\s*([A-Z][A-Z0-9._-]{1,30})\b/i);
    const heading = text.indexOf('Machine Fault');
    const rest = heading < 0 ? '' : text.slice(heading + 'Machine Fault'.length);
    const end = rest.search(/\b(?:Suggested Action|SA\s+\d+|Fault Code)\b/i);
    const description = clean((end < 0 ? rest : rest.slice(0, end)).replace(/^[\s–—-]+/, '')).slice(0, 500);
    if (!description && !tuple && !oem) return null;
    const severity = /\bCritical\b/i.test(text.slice(0, Math.max(heading, 0))) ? 'Critical' :
      /\bLow\b/i.test(text.slice(0, Math.max(heading, 0))) ? 'Low' : 'Unknown';
    return {code: oem ? oem[1] : tuple ? `SPN ${tuple[2]} / FMI ${tuple[3]}` : null,
      spn: tuple ? Number(tuple[2]) : null, fmi: tuple ? Number(tuple[3]) : null,
      sa: tuple ? Number(tuple[1]) : null, description, severity,
      displayed_at: clean(time).slice(0, 100)};
  }
  function parseServiceCardText(value, time = '') {
    const text = clean(value);
    const heading = text.match(/\b(Overdue Service|Upcoming service)\b/i);
    if (!heading) return null;
    const kind = /^Overdue/i.test(heading[1]) ? 'overdue' : 'upcoming';
    const after = text.slice(heading.index + heading[0].length);
    const plan = clean(after.split(/\bOperating hours\b/i)[0]).slice(0, 120);
    const hours = after.match(/\bOperating hours\s+(\d[\d,.]*)\s*h\s+(\d[\d,.]*)\s*h\s+(overdue|remaining)\b/i);
    return {kind, title:heading[1], plan, target_hours:hours ? Number(hours[1].replace(/,/g, '')) : null,
      hours_offset:hours ? Number(hours[2].replace(/,/g, '')) : null,
      displayed_at:clean(time).slice(0, 100)};
  }
  function capture() {
    const asset_id = assetFromUrl(location.href);
    if (!asset_id || window.top !== window) return {capture_status:'wrong_page'};
    const cards = [...document.querySelectorAll('[data-card-body="true"]')].slice(0, 30);
    const faults = [], services = [];
    let visible_count = 0;
    for (const card of cards) {
      if (!card.getClientRects().length || getComputedStyle(card).visibility === 'hidden') continue;
      const heading = card.querySelector('h2')?.textContent?.trim();
      if (!heading) continue;
      visible_count++;
      const time = card.querySelector('time[datetime]')?.getAttribute('datetime');
      if (heading === 'Machine Fault') {
        const fault = parseCardText(card.innerText, time);
        if (fault && faults.length < 20) faults.push(fault);
      } else if (/^(Overdue Service|Upcoming service)$/i.test(heading)) {
        const service = parseServiceCardText(card.innerText, time);
        if (service && services.length < 20) services.push(service);
      }
    }
    return {schema_version:1,source:'trackunit_visible_events_page',asset_id,
      capture_status:faults.length?'visible_fault_cards':'no_visible_fault_cards',
      coverage:'rendered_active_events_only',observed_at:new Date().toISOString(),
      active_event_count:visible_count,faults,services};
  }
  return {assetFromUrl,parseCardText,parseServiceCardText,capture};
})();
if (typeof module !== 'undefined') module.exports = TrackunitFaultPage;
