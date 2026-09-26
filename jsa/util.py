"""Small shared helpers. Standard library only."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = os.environ.get(
    "JSA_USER_AGENT",
    "job-search-agent/1.0 (personal job search; +https://github.com/D0M3N1C0X/job-search-agent)",
)

log = logging.getLogger("jsa")


class FetchError(RuntimeError):
    """Raised when a source cannot be reached or returns an unusable payload."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# Certificate stores move around: a Homebrew or python.org interpreter on macOS
# often ships without a usable CA bundle, which makes every HTTPS call fail with
# CERTIFICATE_VERIFY_FAILED even though curl works fine. Find a real bundle once
# rather than making the user run a post-install script.
_CA_CANDIDATES = [
    "/etc/ssl/cert.pem",                       # macOS system bundle (what curl uses)
    "/etc/ssl/certs/ca-certificates.crt",      # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",        # Fedora/RHEL
    "/usr/local/etc/openssl@3/cert.pem",
    "/opt/homebrew/etc/openssl@3/cert.pem",
]


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if context.cert_store_stats().get("x509_ca", 0):
        return context
    for candidate in [os.environ.get("SSL_CERT_FILE")] + _CA_CANDIDATES:
        if candidate and Path(candidate).exists():
            try:
                context.load_verify_locations(cafile=candidate)
            except OSError:
                continue
            if context.cert_store_stats().get("x509_ca", 0):
                log.debug("using CA bundle %s", candidate)
                return context
    try:
        import certifi  # optional; only used if the environment already has it

        context.load_verify_locations(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - we simply have no better bundle to offer
        log.warning("no CA bundle found — HTTPS verification may fail")
    return context


_SSL = _ssl_context()


def now() -> str:
    """Current UTC timestamp, second precision, ISO-8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return now()[:10]


def days_between(earlier: str | None, later: str | None = None) -> int | None:
    """Whole days between two ISO timestamps. None if either is missing."""
    if not earlier:
        return None
    try:
        a = datetime.fromisoformat(earlier)
        b = datetime.fromisoformat(later) if later else datetime.now(timezone.utc)
    except ValueError:
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return (b - a).days


_HOSTLIKE = re.compile(r"[\w-]+(\.[\w-]+)+(/|$)")


def safe_url(url: str | None) -> str:
    """The URL if it is a web link, otherwise "".

    Posting URLs come from feeds other people write, and they end up in an
    `href`, in `open` on macOS and in a browser. A `javascript:` link runs code
    in the dashboard the moment it is clicked; a `file:` URL or a bare path
    makes `open` launch whatever it names. Only http(s) survives. A scheme-less
    "www.example.com/jobs/1", which is how people paste into `jsa add`, gets
    https added rather than being thrown away.
    """
    value = (url or "").strip()
    if re.match(r"(?i)https?://\S", value):
        return value
    if _HOSTLIKE.match(value):
        return "https://" + value
    return ""


# A Greenhouse board with every description inlined is a few megabytes. Nothing
# legitimate comes close to this; a misbehaving server or a gzip bomb does.
MAX_RESPONSE = 32 * 1024 * 1024


def _read_capped(resp: Any, url: str) -> bytes:
    raw = resp.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise FetchError(f"{url} -> response larger than {MAX_RESPONSE // 2**20} MB, refused")
    if resp.headers.get("Content-Encoding") != "gzip":
        return raw
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        body = inflater.decompress(raw, MAX_RESPONSE + 1)
    except zlib.error as exc:
        raise FetchError(f"{url} -> corrupt gzip body ({exc})") from exc
    if len(body) > MAX_RESPONSE or inflater.unconsumed_tail:
        raise FetchError(f"{url} -> response inflates past {MAX_RESPONSE // 2**20} MB, refused")
    return body


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
    cache_dir: Path | None = None,
    cache_ttl: int = 900,
) -> str:
    """GET a URL and return the decoded body.

    Retries on 429/5xx with exponential backoff. Optionally serves from an
    on-disk cache, which keeps repeated runs (and the test suite) offline-ish
    and polite to the sources.
    """
    # urllib also speaks file:// and ftp://; nothing this tool fetches does.
    if not re.match(r"(?i)https?://", url):
        raise FetchError(f"{url} -> only http(s) URLs are fetched")
    cache_file = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")
        if cache_file.exists() and time.time() - cache_file.stat().st_mtime < cache_ttl:
            return cache_file.read_text(encoding="utf-8")

    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/xml, text/html;q=0.9, */*;q=0.8",
        "Accept-Encoding": "gzip",
        "Accept-Language": "en",
    }
    req_headers.update(headers or {})

    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
                raw = _read_capped(resp, url)
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    body = raw.decode(charset, errors="replace")
                except LookupError:  # a charset Python has never heard of
                    body = raw.decode("utf-8", errors="replace")
            if cache_file is not None:
                cache_file.write_text(body, encoding="utf-8")
            return body
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (403, 404, 410):
                raise FetchError(f"{url} -> HTTP {exc.code}", status=exc.code) from exc
            if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == retries:
                raise FetchError(f"{url} -> HTTP {exc.code}", status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == retries:
                raise FetchError(f"{url} -> {exc}") from exc
        log.debug("retry %s/%s for %s in %.1fs", attempt, retries, url, delay)
        time.sleep(delay)
        delay *= 2
    raise FetchError(f"{url} -> {last_error}")


def http_json(url: str, **kwargs: Any) -> Any:
    body = http_get(url, **kwargs)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise FetchError(f"{url} -> response was not JSON ({exc})") from exc


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n{3,}")

_ENTITIES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#39;": "'", "&apos;": "'", "&rsquo;": "’", "&mdash;": "—",
    "&ndash;": "–", "&hellip;": "…", "&bull;": "•",
}


def html_to_text(html: str) -> str:
    """Flatten an HTML job description into readable plain text."""
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "• ", text)
    text = _TAG.sub(" ", text)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = _WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANKS.sub("\n\n", text).strip()


def slugify(value: str, max_length: int = 48) -> str:
    """Filesystem-safe slug, used for output filenames."""
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return (value[:max_length].rstrip("_") or "item")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
