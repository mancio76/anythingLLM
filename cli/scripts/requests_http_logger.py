# requests_http_logger.py
# -*- coding: utf-8 -*-
"""
Safe logger for all requests.* calls.

- Logs each HTTP call in chronological order into a single readable file.
- Generates a .sh with equivalent curl commands (in order).
- Does NOT consume response bodies when stream=True.
- Only change needed in your app: call enable_requests_logging(...) at startup.

Usage (at the VERY top of your script, before using requests):
    from requests_http_logger import enable_requests_logging
    enable_requests_logging(
        log_path="anythingllm_trace.log",
        curl_script_path="anythingllm_calls.sh",
        redact_secrets=True,
        max_body_chars=20000,
        also_write_jsonl=None,
        host_filter=None  # e.g. "anythingllm.local" if you want to limit logging
    )
"""
import json
import os
import shlex
import time
import itertools
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse

import requests

# ---- security redactions ----
REDACT_HEADERS = {"authorization", "x-api-key", "proxy-authorization", "cookie", "set-cookie"}

# ---- sequence to preserve order ----
_SEQ = itertools.count(1)

# ---------------- utilities ----------------
def _redact_headers(headers: Dict[str, str], redact: bool) -> Dict[str, str]:
    if not headers:
        return {}
    if not redact:
        return dict(headers)
    out = {}
    for k, v in headers.items():
        out[k] = "****REDACTED****" if k.lower() in REDACT_HEADERS else v
    return out

def _detect_payload(kwargs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    # returns (type, str_payload) with type in {json, data, files, None}
    if "json" in kwargs and kwargs["json"] is not None:
        try:
            return "json", json.dumps(kwargs["json"], ensure_ascii=False, indent=2)
        except Exception:
            return "json", str(kwargs["json"])
    if "data" in kwargs and kwargs["data"] is not None:
        d = kwargs["data"]
        if isinstance(d, (dict, list, tuple)):
            try:
                return "data", json.dumps(d, ensure_ascii=False, indent=2)
            except Exception:
                return "data", str(d)
        try:
            return "data", d.decode("utf-8", "replace") if isinstance(d, (bytes, bytearray)) else str(d)
        except Exception:
            return "data", "<unprintable data>"
    if "files" in kwargs and kwargs["files"]:
        # don't serialize file content; just list field -> filename
        files_desc = {}
        for key, val in kwargs["files"].items():
            fname = None
            try:
                if isinstance(val, (list, tuple)) and len(val) >= 1:
                    fname = val[0]
                else:
                    fname = "STREAM"
            except Exception:
                fname = "STREAM"
            files_desc[key] = {"filename": fname}
        return "files", json.dumps(files_desc, ensure_ascii=False, indent=2)
    return None, None

def _headers_to_shell_flags(headers: Dict[str, str]) -> str:
    return " ".join(f"-H {shlex.quote(f'{k}: {v}')}" for k, v in (headers or {}).items())

def _payload_to_curl_flags(ptype: Optional[str], payload: Optional[str], kwargs: Dict[str, Any]) -> str:
    if ptype in ("json", "data"):
        return f"--data {shlex.quote(payload or '')}"
    if ptype == "files":
        flags = []
        for key, val in (kwargs.get("files") or {}).items():
            if isinstance(val, (list, tuple)) and len(val) >= 1:
                fname = val[0]
                flags.append(f"-F {shlex.quote(f'{key}=@{fname}')}")
            else:
                flags.append(f"-F {shlex.quote(f'{key}=@FILE')}")
        data = kwargs.get("data")
        if isinstance(data, dict):
            for k, v in data.items():
                flags.append(f"-F {shlex.quote(f'{k}={v}')}")
        return " ".join(flags)
    return ""

def _build_curl(method: str, url: str, headers: Dict[str, str], ptype: Optional[str], payload: Optional[str], kwargs: Dict[str, Any]) -> str:
    m = method.upper()
    mflag = f"-X {m}" if m != "GET" else ""
    return " ".join([p for p in [
        "curl", "-sS", "-i",
        mflag,
        _headers_to_shell_flags(headers),
        _payload_to_curl_flags(ptype, payload, kwargs),
        shlex.quote(url)
    ] if p])

def _truncate(text: Optional[str], limit: Optional[int]) -> Optional[str]:
    if text is None or limit is None:
        return text
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text)-limit} chars]"

def _pretty_headers(headers: Dict[str, str]) -> str:
    if not headers:
        return "  (none)\n"
    return "\n".join(f"  {k}: {v}" for k, v in headers.items()) + "\n"

def _indent_block(text: str, spaces: int = 2) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in (text or "").splitlines())

def _open_append(path: str):
    # line-buffered append
    return open(path, "a", encoding="utf-8", buffering=1)

# ---------------- public API ----------------
def enable_requests_logging(
    log_path: str = "anythingllm_trace.log",
    curl_script_path: Optional[str] = "anythingllm_calls.sh",
    redact_secrets: bool = True,
    max_body_chars: Optional[int] = 20000,
    also_write_jsonl: Optional[str] = None,
    host_filter: Optional[str] = None,
):
    """
    Patch requests so every call is logged and a curl is generated.

    IMPORTANT: call this once, at process start, before using requests.
    """
    # prepare files
    if not os.path.exists(log_path):
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("# AnythingLLM HTTP Trace\n")
            f.write(f"# Started: {datetime.now(timezone.utc).isoformat()}\n\n")

    if curl_script_path and not os.path.exists(curl_script_path):
        with open(curl_script_path, "w", encoding="utf-8") as f:
            f.write("#!/usr/bin/env bash\nset -euo pipefail\n\n")
        try:
            os.chmod(curl_script_path, 0o755)
        except Exception:
            pass

    if also_write_jsonl and not os.path.exists(also_write_jsonl):
        with open(also_write_jsonl, "w", encoding="utf-8"):
            pass

    # store original
    orig_request = requests.Session.request

    def wrapped(session, method, url, **kwargs):
        # host filter
        if host_filter:
            try:
                host = urlparse(url).hostname or ""
            except Exception:
                host = ""
            if host != host_filter:
                return orig_request(session, method, url, **kwargs)

        seq = next(_SEQ)
        ts = datetime.now(timezone.utc)
        t0 = time.time()

        # effective headers (session + per-call)
        headers = {}
        if isinstance(getattr(session, "headers", None), dict):
            headers.update(session.headers)
        if isinstance(kwargs.get("headers"), dict):
            headers.update(kwargs["headers"])
        redacted = _redact_headers(headers, redact_secrets)

        ptype, payload = _detect_payload(kwargs)
        curl_cmd = _build_curl(method, url, redacted, ptype, payload, kwargs)

        # do NOT touch kwargs or mutate session
        response = None
        exc = None
        try:
            response = orig_request(session, method, url, **kwargs)
            return response
        except Exception as e:
            exc = repr(e)
            raise
        finally:
            dt = round(time.time() - t0, 6)

            # response details (avoid draining body on stream=True)
            stream = bool(kwargs.get("stream", False))
            status = None
            resp_headers = {}
            ctype = ""
            body_text = None

            if response is not None:
                try:
                    status = response.status_code
                except Exception:
                    status = None
                try:
                    resp_headers = dict(response.headers or {})
                except Exception:
                    resp_headers = {}
                try:
                    ctype = response.headers.get("Content-Type", "") if response.headers else ""
                except Exception:
                    ctype = ""
                if not stream:
                    try:
                        body_text = response.text if response.content is not None else ""
                    except Exception:
                        body_text = "<unreadable response body>"
                else:
                    body_text = "(stream=True; body not read)"

            # pretty truncation for human log
            pp_payload = payload if ptype in {"json", "data"} else payload  # files already summarized
            if max_body_chars is not None:
                pp_payload = _truncate(pp_payload, max_body_chars)
                if body_text is not None:
                    body_text = _truncate(body_text, max_body_chars)

            # ---- human log ----
            with _open_append(log_path) as lf:
                lf.write(f"--- CALL #{seq} @ {ts.isoformat()} ---\n")
                lf.write("REQUEST:\n")
                lf.write(f"  METHOD: {method.upper()}\n")
                lf.write(f"  URL: {url}\n")
                lf.write("  HEADERS:\n")
                lf.write(_pretty_headers(redacted))
                lf.write(f"  PAYLOAD_TYPE: {ptype or '(none)'}\n")
                if ptype in {"json", "data"} and pp_payload:
                    lf.write("  PAYLOAD:\n")
                    lf.write(_indent_block(pp_payload, 4) + "\n")
                elif ptype == "files":
                    lf.write("  PAYLOAD: multipart/form-data (see file list below)\n")
                    lf.write(_indent_block(payload or "", 4) + "\n")
                else:
                    lf.write("  PAYLOAD: (none)\n")

                lf.write("\nCURL EQUIVALENT:\n")
                lf.write(_indent_block(curl_cmd, 2) + "\n")

                lf.write("\nRESPONSE:\n")
                if response is not None:
                    lf.write(f"  STATUS: {status}\n")
                    lf.write("  HEADERS:\n")
                    lf.write(_pretty_headers(resp_headers))
                    lf.write(f"  CONTENT_TYPE: {ctype}\n")
                    lf.write("  BODY:\n")
                    lf.write(_indent_block(body_text or "", 4) + "\n")
                else:
                    lf.write("  (no response: exception occurred)\n")

                if exc is not None:
                    lf.write("\nEXCEPTION:\n")
                    lf.write(_indent_block(exc, 2) + "\n")

                lf.write(f"\n=== END CALL #{seq} (duration {dt}s) ===\n\n")

            # ---- curl script ----
            if curl_script_path:
                with _open_append(curl_script_path) as sf:
                    sf.write(f"# --- CALL #{seq} {ts.isoformat()} ---\n")
                    sf.write(f"# {method.upper()} {url}\n")
                    for k, v in redacted.items():
                        sf.write(f"# Header: {k}: {v}\n")
                    if ptype in {"json", "data"} and (payload is not None):
                        compact = payload
                        if ptype == "json":
                            try:
                                compact = json.dumps(json.loads(payload), ensure_ascii=False)
                            except Exception:
                                compact = payload
                        # keep a short preview in comments
                        prev = compact if max_body_chars is None else _truncate(compact, min(2000, max_body_chars))
                        sf.write("# Body:\n# " + (prev or "") + "\n")
                    elif ptype == "files":
                        sf.write("# Body: multipart/form-data (-F flags below)\n")
                    sf.write(curl_cmd + "\n\n")

            # ---- optional jsonl ----
            if also_write_jsonl:
                entry = {
                    "seq": seq,
                    "ts": ts.isoformat(),
                    "duration_sec": dt,
                    "request": {
                        "method": method.upper(),
                        "url": url,
                        "headers": redacted,
                        "payload_type": ptype,
                        "payload": payload,
                    },
                    "curl": curl_cmd,
                }
                if response is not None:
                    entry["response"] = {
                        "status_code": status,
                        "headers": resp_headers,
                        "content_type": ctype,
                        "body": None if stream else (body_text or ""),
                    }
                if exc is not None:
                    entry["exception"] = exc
                with _open_append(also_write_jsonl) as jf:
                    jf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # safe monkey-patch using closure (NOT a bound method)
    requests.Session.request = wrapped
