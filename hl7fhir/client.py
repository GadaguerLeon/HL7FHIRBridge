from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

PUBLIC_TEST_SERVER = "https://hapi.fhir.org/baseR4"
FHIR_JSON = "application/fhir+json"


class FHIRError(RuntimeError):
    def __init__(self, status: int, outcome: dict | None, message: str):
        super().__init__(message)
        self.status = status
        self.outcome = outcome


class FHIRClient:
    def __init__(self, base_url: str = PUBLIC_TEST_SERVER, token: str | None = None, timeout: float = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def read(self, resource_type: str, resource_id: str) -> dict:
        return self._request("GET", f"{resource_type}/{urllib.parse.quote(resource_id)}")

    def search(self, resource_type: str, **params: str) -> dict:
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"{resource_type}?{query}" if query else resource_type)

    def create(self, resource: dict) -> dict:
        return self._request("POST", resource["resourceType"], resource)

    def transaction(self, bundle: dict) -> dict:
        if bundle.get("type") not in ("transaction", "batch"):
            raise ValueError("bundle type must be 'transaction' or 'batch'")
        return self._request("POST", "", bundle)

    def capabilities(self) -> dict:
        return self._request("GET", "metadata")

    @staticmethod
    def entries(bundle: dict) -> list[dict]:
        return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}/{path}" if path else self.base_url
        headers = {"Accept": FHIR_JSON}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = FHIR_JSON
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
                return json.loads(payload) if payload else {}
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                outcome = json.loads(raw)
            except (ValueError, TypeError):
                outcome = None
            detail = ""
            if outcome and outcome.get("resourceType") == "OperationOutcome":
                detail = "; ".join(i.get("diagnostics", "") for i in outcome.get("issue", []))
            raise FHIRError(err.code, outcome, f"{method} {url} HTTP {err.code} {detail}".strip()) from err
