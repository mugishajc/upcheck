"""Performs a single HTTP check. Knows nothing about the database."""

import time
from dataclasses import dataclass

import requests

MAX_BODY_BYTES = 512 * 1024  # enough to look for a keyword without pulling huge pages


@dataclass(frozen=True)
class CheckResult:
    is_up: bool
    status_code: int | None
    latency_ms: int | None
    error: str | None = None


def check_url(
    url: str,
    timeout: float = 10,
    expected_status: int | None = None,
    keyword: str | None = None,
    session: requests.Session | None = None,
    user_agent: str = "flask-url-monitor",
) -> CheckResult:
    http = session or requests
    started = time.perf_counter()
    try:
        response = http.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            stream=keyword is not None,
            headers={"User-Agent": user_agent},
        )
    except requests.Timeout:
        return CheckResult(False, None, None, f"Timed out after {timeout}s")
    except requests.ConnectionError as exc:
        return CheckResult(False, None, None, f"Connection error: {_short(exc)}")
    except requests.RequestException as exc:
        return CheckResult(False, None, None, f"Request failed: {_short(exc)}")

    latency_ms = round((time.perf_counter() - started) * 1000)
    status = response.status_code

    try:
        if expected_status is not None:
            ok = status == expected_status
            error = None if ok else f"Expected HTTP {expected_status}, got {status}"
        else:
            ok = status < 400
            error = None if ok else f"HTTP {status}"

        if ok and keyword:
            body = _read_text(response)
            if keyword not in body:
                ok, error = False, f"Keyword {keyword!r} not found"
    finally:
        response.close()

    return CheckResult(ok, status, latency_ms, error)


def _read_text(response: requests.Response) -> str:
    chunks, size = [], 0
    for chunk in response.iter_content(chunk_size=16384):
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BODY_BYTES:
            break
    encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def _short(exc: Exception, limit: int = 200) -> str:
    text = str(exc)
    return text if len(text) <= limit else text[: limit - 3] + "..."
