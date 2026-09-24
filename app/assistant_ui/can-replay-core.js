/* Shared pure time/evidence operations; missing or stale readings are never zero-filled. */
const CanReplayCore = (() => {
  function atTime(signal, at, maxAge = 2) {
    const points = signal?.points || [];
    let lo = 0, hi = points.length - 1, hit = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (points[mid].t <= at) { hit = points[mid]; lo = mid + 1; } else hi = mid - 1;
    }
    return hit && at - hit.t <= maxAge && hit.value !== null ? hit : null;
  }
  function clock(seconds) { return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`; }
  function visibleEvidence(data, at) {
    return data.signals.map(signal => ({key: signal.key, name: signal.name, unit: signal.unit,
      point: atTime(signal, at, signal.key === 'hours' ? 15 : 2)}));
  }
  return {atTime, clock, visibleEvidence};
})();
if (typeof module !== 'undefined') module.exports = CanReplayCore;
