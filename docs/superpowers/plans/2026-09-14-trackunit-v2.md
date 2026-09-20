# Trackunit v2 Implementation Plan

> Execute inline in this session; scope is authentication and local configuration.

**Goal:** Support client_credentials and automatic token renewal without user intervention.

**Architecture:** Keep TrackunitClient's public API. Serialize process-local token exchange, cache tokens by credentials and grant, renew on demand before expiry and retry a rejected token once within the existing retry budget. Keep legacy password flow explicit.

**Tech Stack:** Python, httpx, pytest, dotenv.

## Constraints
- No credentials or access tokens in tracked files or output.
- Only read-only real API checks; no background sync enabled.
- Do not claim historical data or fault integrations are complete.

## Work
- [x] Add isolated tests for v2 request body, cache reuse, expiry, 401 retry, error redaction, credential changes, legacy mode.
- [x] Implement grant selection, safe errors, token expiry and process-local lock in app/trackunit_client.py.
- [x] Update .env.example and README.md; place local credentials only in ignored .env.
- [x] Run tests/test_trackunit_client.py and full pytest; report existing failures separately.
- [x] Verify local client authentication and fleet snapshot once; report only counts and status.

## Verification
- Authentication tests: 9 passed.
- Full suite: 68 passed, 3 existing date-dependent failures in query_engine/trend_analysis.
- Project client live check: v2 token success, cross-client cache reused, fleet page 1 returned 100 records.
- Local .env is git-ignored. DATA_SOURCE remains mock until the real-data UI workflow is validated; auto-sync is disabled.
- Added tests/conftest.py to disable dotenv loading during unit tests.
