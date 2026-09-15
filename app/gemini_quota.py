"""Extract quota categories without forwarding arbitrary upstream error text."""
import math
import re


def quota_failure(response):
    if response.status_code != 429:
        return None
    result = {'kind': 'quota_unknown', 'limits': []}
    try:
        details = response.json()['error'].get('details', [])
        if not isinstance(details, list):
            return result
    except (ValueError, TypeError, KeyError, AttributeError):
        return result
    retry_seconds = None
    for detail in details[:20]:
        if not isinstance(detail, dict):
            continue
        if detail.get('@type') == 'type.googleapis.com/google.rpc.RetryInfo':
            delay = detail.get('retryDelay', '')
            if isinstance(delay, str) and re.fullmatch(r'\d{1,5}(\.\d{1,9})?s', delay):
                retry_seconds = math.ceil(float(delay[:-1]))
        if detail.get('@type') != 'type.googleapis.com/google.rpc.QuotaFailure':
            continue
        violations = detail.get('violations', [])
        if not isinstance(violations, list):
            continue
        for violation in violations[:20]:
            if not isinstance(violation, dict):
                continue
            quota_id = violation.get('quotaId', '')
            if not isinstance(quota_id, str) or not re.fullmatch(r'Generate[A-Za-z0-9-]{1,180}', quota_id):
                continue
            window = 'day' if 'PerDay' in quota_id else 'minute' if 'PerMinute' in quota_id else None
            if window is None:
                continue
            measure = 'requests' if 'Requests' in quota_id else 'tokens' if 'Tokens' in quota_id else 'unknown'
            if measure == 'unknown':
                continue
            item = {'window': window, 'measure': measure}
            value = violation.get('quotaValue')
            if isinstance(value, str) and re.fullmatch(r'\d{1,12}', value):
                item['limit'] = int(value)
            if item not in result['limits']:
                result['limits'].append(item)
    if any(item.get('limit') == 0 for item in result['limits']):
        result['kind'] = 'quota_unavailable'
    elif any(item['window'] == 'day' for item in result['limits']):
        result['kind'] = 'daily_quota'
    elif result['limits']:
        result['kind'] = 'minute_quota'
    # A short RetryInfo interval cannot override an exhausted daily/zero quota.
    if result['kind'] == 'minute_quota' and retry_seconds is not None:
        result['retry_after_seconds'] = retry_seconds
    return result
