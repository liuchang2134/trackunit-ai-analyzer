import base64
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv(override=True)


class TrackunitError(Exception):
    pass


class TrackunitClient:
    _shared_access_token: str | None = None
    _shared_expires_at = 0.0
    _shared_credential_key: tuple[str, str, str, str, str] | None = None

    def __init__(self, timeout_seconds: float = 30.0, retries: int = 2):
        self.base_url = os.getenv("TRACKUNIT_BASE_URL", "").rstrip("/")
        self.auth_url = os.getenv("TRACKUNIT_AUTH_URL", "")
        self.client_id = os.getenv("TRACKUNIT_CLIENT_ID", "")
        self.client_secret = os.getenv("TRACKUNIT_CLIENT_SECRET", "")
        self.scope = os.getenv("TRACKUNIT_SCOPE", "api")
        self.username = os.getenv("TRACKUNIT_USERNAME", "")
        self.password = os.getenv("TRACKUNIT_PASSWORD", "")
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self._access_token: str | None = None
        self._expires_at = 0.0

    def _credential_key(self) -> tuple[str, str, str, str, str]:
        return (self.auth_url, self.client_id, self.username, self.scope, self.client_secret)

    def _validate_credentials(self) -> None:
        required = [
            self.auth_url,
            self.client_id,
            self.client_secret,
            self.username,
            self.password,
        ]
        if not all(required):
            raise TrackunitError("Trackunit credentials are missing")

    def get_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token

        credential_key = self._credential_key()
        if (
            self.__class__._shared_access_token
            and self.__class__._shared_credential_key == credential_key
            and time.time() < self.__class__._shared_expires_at - 60
        ):
            self._access_token = self.__class__._shared_access_token
            self._expires_at = self.__class__._shared_expires_at
            return self._access_token

        self._validate_credentials()
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("ascii")).decode("ascii")
        body = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "scope": self.scope,
        }
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = httpx.post(self.auth_url, data=body, headers=headers, timeout=self.timeout_seconds)
        except httpx.HTTPError as exc:
            raise TrackunitError("Trackunit authentication failed") from exc

        if response.status_code != 200:
            raise TrackunitError("Trackunit authentication failed")

        data = response.json()
        token = data.get("access_token")
        if not token:
            raise TrackunitError("Trackunit authentication failed")

        self._access_token = token
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        self.__class__._shared_access_token = token
        self.__class__._shared_expires_at = self._expires_at
        self.__class__._shared_credential_key = credential_key
        return token

    def _resolve_endpoint(self, endpoint: str) -> str:
        if not endpoint:
            raise TrackunitError("Trackunit API endpoint is not configured")
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if not self.base_url:
            raise TrackunitError("Trackunit API endpoint is not configured")
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        url = self._resolve_endpoint(endpoint)
        last_error: Exception | None = None

        for attempt in range(self.retries + 1):
            try:
                token = self.get_token()
                request_kwargs = dict(kwargs)
                headers = dict(request_kwargs.pop("headers", {}))
                headers["Authorization"] = f"Bearer {token}"
                headers.setdefault("Accept", "application/json")
                response = httpx.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout_seconds,
                    **request_kwargs,
                )
                if response.status_code == 401 and attempt < self.retries:
                    self._access_token = None
                    self.__class__._shared_access_token = None
                    continue
                if response.status_code == 429:
                    if attempt < self.retries:
                        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                        time.sleep(retry_after or 1.0 * (attempt + 1))
                        continue
                    raise TrackunitError("Trackunit API rate limit reached (429). Please wait and try again.")
                if response.status_code >= 400:
                    raise TrackunitError(f"Trackunit API request failed with status code {response.status_code}")
                return response.json()
            except TrackunitError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                time.sleep(0.5 * (attempt + 1))

        raise TrackunitError(f"Trackunit API request failed: {last_error}")

    def get_configured_endpoint(self, env_name: str) -> str:
        endpoint = os.getenv(env_name, "")
        if not endpoint:
            raise TrackunitError("Trackunit API endpoint is not configured")
        return endpoint

    def get_machine_list(self) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_FLEET_SNAPSHOT_ENDPOINT")
        if "{page}" not in endpoint:
            return self.request("GET", endpoint)

        items: list[Any] = []
        page = 1
        while True:
            payload = self.request("GET", _format_endpoint(endpoint, page=str(page)))
            page_items = _extract_items(payload)
            if not page_items:
                break
            items.extend(page_items)

            links = payload.get("links", []) if isinstance(payload, dict) else []
            has_next = any(link.get("rel") == "next" for link in links if isinstance(link, dict))
            if not has_next:
                break
            page += 1
        return items

    def get_single_machine_detail(self, machine_query: str) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_SINGLE_ASSET_ENDPOINT")
        return self.request("GET", _format_endpoint(endpoint, machine_query=machine_query))

    def get_telemetry(self, machine_query: str | None = None, start: str | None = None, end: str | None = None) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_TIME_SERIES_ENDPOINT")
        params = _clean_params({"machine_id": machine_query, "start": start, "end": end})
        return self.request("GET", _format_endpoint(endpoint, machine_query=machine_query or ""), params=params)

    def get_faults(self, machine_query: str | None = None, start: str | None = None, end: str | None = None) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_FAULTS_ENDPOINT")
        params = _clean_params({"machine_id": machine_query, "start": start, "end": end})
        return self.request("GET", _format_endpoint(endpoint, machine_query=machine_query or ""), params=params)

    def get_can_faults(self, machine_query: str | None = None, start: str | None = None, end: str | None = None) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_CAN_FAULTS_ENDPOINT")
        params = _clean_params({"machine_id": machine_query, "start": start, "end": end})
        return self.request("GET", _format_endpoint(endpoint, machine_query=machine_query or ""), params=params)

    def get_machine_faults(self, machine_query: str | None = None, start: str | None = None, end: str | None = None) -> Any:
        endpoint = self.get_configured_endpoint("TRACKUNIT_MACHINE_FAULTS_ENDPOINT")
        params = _clean_params({"machine_id": machine_query, "start": start, "end": end})
        return self.request("GET", _format_endpoint(endpoint, machine_query=machine_query or ""), params=params)


def _format_endpoint(endpoint: str, **values: str) -> str:
    # TODO: Replace placeholder names when the exact Trackunit endpoint templates are finalized.
    formatted = endpoint
    for key, value in values.items():
        formatted = formatted.replace("{" + key + "}", value)
        formatted = formatted.replace("{" + key.upper() + "}", value)
    return formatted


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value not in {None, ""}}


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def _extract_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("equipment", "content", "items", "data", "results", "faults", "faultCode"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    return [payload]
