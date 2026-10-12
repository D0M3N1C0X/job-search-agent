"""A small Supabase client: PostgREST tables and Storage, standard library only.

The worker talks to Supabase with the service-role key, which bypasses
row-level security. It lives in the worker's environment and nowhere else:
never in the repository, never in a browser.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..util import _SSL, USER_AGENT, FetchError

BATCH = 500  # rows per upsert request


class Supabase:
    def __init__(self, url: str, key: str, *, timeout: int = 60) -> None:
        self.base = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "Supabase":
        url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url.startswith("https://") or not key:
            raise SystemExit("Set SUPABASE_URL (https://...) and SUPABASE_SERVICE_ROLE_KEY.")
        return cls(url, key)

    # ------------------------------------------------------------- transport

    def _call(self, method: str, path: str, *, body: Any = None, headers: dict[str, str] | None = None,
              raw: bytes | None = None, retries: int = 3) -> bytes:
        url = self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        hdrs = {"apikey": self.key, "User-Agent": USER_AGENT}
        if self.key.startswith("eyJ"):
            # The legacy service_role key is a JWT and goes in both headers; the
            # newer sb_secret_ keys are not JWTs and go in `apikey` alone.
            hdrs["Authorization"] = f"Bearer {self.key}"
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        delay = 1.0
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=hdrs)  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL) as resp:  # noqa: S310
                    return resp.read()
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                    raise FetchError(f"{method} {path} -> HTTP {exc.code}: {detail}", status=exc.code) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt == retries:
                    raise FetchError(f"{method} {path} -> {exc}") from exc
            time.sleep(delay)
            delay *= 2
        raise FetchError(f"{method} {path} -> gave up")

    # ----------------------------------------------------------------- tables

    def select(self, table: str, query: dict[str, str] | None = None) -> list[dict[str, Any]]:
        qs = urllib.parse.urlencode(query or {}, safe="(),.*:")
        return json.loads(self._call("GET", f"/rest/v1/{table}?{qs}") or b"[]")

    def upsert(self, table: str, rows: list[dict[str, Any]], *, on_conflict: str) -> int:
        for start in range(0, len(rows), BATCH):
            self._call("POST", f"/rest/v1/{table}?on_conflict={on_conflict}", body=rows[start:start + BATCH],
                       headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
        return len(rows)

    def update(self, table: str, filters: dict[str, str], values: dict[str, Any]) -> None:
        qs = urllib.parse.urlencode(filters, safe="(),.*:")
        self._call("PATCH", f"/rest/v1/{table}?{qs}", body=values, headers={"Prefer": "return=minimal"})

    def delete(self, table: str, filters: dict[str, str]) -> None:
        if not filters:
            raise ValueError("refusing to delete a whole table")
        qs = urllib.parse.urlencode(filters, safe="(),.*:")
        self._call("DELETE", f"/rest/v1/{table}?{qs}", headers={"Prefer": "return=minimal"})

    # ---------------------------------------------------------------- storage

    def download(self, bucket: str, path: str) -> bytes:
        return self._call("GET", f"/storage/v1/object/{bucket}/{urllib.parse.quote(path)}")

    def remove(self, bucket: str, paths: list[str]) -> None:
        self._call("DELETE", f"/storage/v1/object/{bucket}", body={"prefixes": paths})
