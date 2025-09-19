
# -*- coding: utf-8 -*-
"""
Modulo 3: Upload documenti e gestione cartelle AnythingLLM.
Endpoint fissi su /api/v1 come da specifica utente.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple, List, Dict
import mimetypes
import requests

DEFAULT_API_BASE = "/api/v1"

# --- Tentativo di usare il logger esterno, fallback a requests.Session() ---
try:
    import requests_http_logger  # non modificare questo file
except Exception:
    requests_http_logger = None

@dataclass
class AnythingLLMClient:
    base_url: str
    api_key: str
    api_base: str = DEFAULT_API_BASE
    timeout: int = 60
    verbose: bool = False
    session: Optional[requests.Session] = None

    def __post_init__(self):
        if requests_http_logger:
            for fname in ("get_logged_session","make_logged_session","session","get_session","make_session"):
                if hasattr(requests_http_logger, fname):
                    try:
                        self.session = getattr(requests_http_logger, fname)(
                            base_url=self.base_url,
                            api_key=self.api_key,
                            timeout=self.timeout,
                            verbose=self.verbose,
                        )
                        break
                    except TypeError:
                        continue
                    except Exception:
                        continue
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            if self.verbose:
                print("[LOGGER] Fallback a requests.Session() (logger non disponibile)")

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def post_json(self, path: str, payload: dict) -> dict:
        r = self.session.post(self._url(path), json=payload, timeout=self.timeout, headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        status = r.status_code
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        data["__status__"] = status
        if self.verbose:
            print(f"   [HTTP POST] POST {self._url(path)} -> {status}")
            ctype = r.headers.get("Content-Type","")
            print(f"   [HTTP POST] Content-Type: {ctype} Length: {len(r.content)}")
        return data

    def post_multipart(self, path: str, files: dict, data: Optional[dict]=None) -> dict:
        r = self.session.post(self._url(path), files=files, data=data or {}, timeout=self.timeout, headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        status = r.status_code
        try:
            data_out = r.json()
        except Exception:
            data_out = {"raw": r.text}
        data_out["__status__"] = status
        if self.verbose:
            print(f"   [HTTP POST] POST {self._url(path)} -> {status}")
            ctype = r.headers.get("Content-Type","")
            print(f"   [HTTP POST] Content-Type: {ctype} Length: {len(r.content)}")
        return data_out

    def get_json(self, path: str) -> dict:
        r = self.session.get(self._url(path), timeout=self.timeout, headers={
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        })
        status = r.status_code
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        data["__status__"] = status
        if self.verbose:
            print(f"   [HTTP GET] GET {self._url(path)} -> {status}")
            ctype = r.headers.get("Content-Type","")
            print(f"   [HTTP GET] Content-Type: {ctype} Length: {len(r.content)}")
        return data

def create_folder_if_needed(client: AnythingLLMClient, name: str) -> str:
    """
    Crea la cartella tramite /api/v1/document/create-folder.
    Considera OK anche il caso 'Folder by that name already exists' (idempotente).
    """
    path = f"{client.api_base}/document/create-folder"
    res = client.post_json(path, {"name": name})
    status = res.get("__status__")
    success = res.get("success") is True
    if status == 200 and success:
        return name
    # Idempotenza: se la cartella esiste già, consideriamo OK
    message = (res.get("message") or res.get("error") or "").lower()
    if status in (400,409,500) and "already exists" in message:
        if client.verbose:
            print(f"   [FOLDER] '{name}' esiste già: procedo.")
        return name
    raise RuntimeError(f"Creazione folder fallita per '{name}'. Risposta: {res}")

def _validate_upload_response(filename: str, res: dict) -> tuple[bool,str,Optional[str]]:
    """
    Validazione permissiva come richiesto: verifica che almeno un documento
    in 'documents' abbia title == filename. Restituisce (ok, info, location).
    """
    if res.get("__status__") != 200:
        return (False, f"HTTP status {res.get('__status__')}", None)
    if not res.get("success", False):
        return (False, f"success={res.get('success')} error={res.get('error')}", None)
    docs = res.get("documents")
    if not isinstance(docs, list) or len(docs) == 0:
        return (False, "documents mancante o vuoto", None)
    first_title = None
    for d in docs:
        t = d.get("title")
        if first_title is None:
            first_title = t
        if t == filename:
            return (True, "ok", d.get("location"))
    return (False, f"title mismatch: expected '{filename}' got '{first_title}'", None)

def upload_files_to_default(client: AnythingLLMClient, files: Iterable[Path], verbose: bool=False) -> List[Dict]:
    """
    Carica tutti i file su 'custom-documents'.
    Ritorna una lista di dict: {filename, location}
    """
    results: List[Dict] = []
    upload_path = f"{client.api_base}/document/upload"
    for p in files:
        mime, _ = mimetypes.guess_type(str(p))
        mime = mime or "application/octet-stream"
        if verbose:
            print(f"   ⬆️  Upload: {p.name} ({mime}) -> custom-documents")
        with p.open("rb") as fh:
            files_payload = {"file": (p.name, fh, mime)}
            data = {"name": "custom-documents"}
            res = client.post_multipart(upload_path, files=files_payload, data=data)
        ok, info, location = _validate_upload_response(p.name, res)
        if ok:
            if verbose:
                print(f"   [UPLOAD OK] {p.name} -> location='{location}'")
            results.append({"filename": p.name, "location": location})
        else:
            # Non bloccare subito: log warn e prosegui, ma se nessuno va ok falliremo alla fine
            print(f"   [UPLOAD WARN] {p.name} -> {info}. Risposta: {res}")
    if not results:
        raise RuntimeError("Nessun file caricato con esito positivo.")
    return results

def move_files_to_folder(client: AnythingLLMClient, target_folder: str, uploaded: List[Dict], verbose: bool=False) -> List[Dict]:
    """
    Sposta i file da 'custom-documents' al folder target usando /api/v1/document/move-files.
    Aggiorna le location nel risultato.
    """
    move_path = f"{client.api_base}/document/move-files"
    moves = []
    final_results: List[Dict] = []
    for item in uploaded:
        loc = item.get("location")
        if not loc or not loc.startswith("custom-documents/"):
            # senza location precisa non possiamo costruire il path di destinazione
            print(f"   [MOVE SKIP] Impossibile spostare '{item.get('filename')}' (location assente).")
            continue
        basename = loc.split("/", 1)[1]
        to_loc = f"{target_folder}/{basename}"
        moves.append({"from": loc, "to": to_loc})
        final_results.append({"filename": item["filename"], "location": to_loc})
    if not moves:
        if verbose:
            print("   [MOVE] Nessun file da spostare.")
        return final_results
    payload = {"files": moves}
    res = client.post_json(move_path, payload)
    if res.get("__status__") == 200 and res.get("success") is True:
        if verbose:
            print(f"   [MOVE OK] Spostati {len(moves)} file nel folder '{target_folder}'.")
        return final_results
    raise RuntimeError(f"Spostamento file fallito verso '{target_folder}'. Risposta: {res}")
