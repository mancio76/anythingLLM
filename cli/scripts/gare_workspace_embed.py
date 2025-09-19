
# -*- coding: utf-8 -*-
"""
Modulo: Workspace & Embedding per AnythingLLM (tutte le API sotto /api/v1)
- Crea/riusa il workspace
- Triggera l'embed per OGNI file (senza polling di stato)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional

# Reuse client from uploader
from gare_anythingllm_upload import AnythingLLMClient

def _slugify(name: str) -> str:
    import re
    s = name.strip().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s or 'workspace'

def _find_workspace_by_name(client: AnythingLLMClient, name: str, verbose: bool=False) -> Optional[Dict[str, Any]]:
    # GET /api/v1/workspaces  -> può restituire list o dict con chiave 'workspaces'
    path = f"{client.api_base}/workspaces"
    if verbose:
        print(f"   [HTTP GET] GET {client.base_url.rstrip('/')}{path}")
    res = client.get_json(path)
    items = None
    if isinstance(res, dict):
        items = res.get("workspaces") or res.get("data") or res.get("items")
    if items is None:
        items = res if isinstance(res, list) else []
    for w in items:
        if (w.get("name") or "").strip().lower() == name.strip().lower():
            return w
    return None

def _create_workspace(client: AnythingLLMClient, name: str, cfg_workspace: Optional[dict], verbose: bool=False) -> Dict[str, Any]:
    # POST /api/v1/workspace/new  body: {"name": "<workspace>"}
    payload = {"name": name}
    # Se in futuro serviranno altri campi dalla config, li si potrà aggiungere qui in modo opzionale.
    path = f"{client.api_base}/workspace/new"
    if verbose:
        print(f"   [HTTP POST] POST {client.base_url.rstrip('/')}{path}")
    res = client.post_json(path, payload)
    return res if isinstance(res, dict) else {"raw": res}

def _extract_slug(workspace_obj: Dict[str, Any], workspace_name: str) -> str:
    # Prova diverse chiavi comuni, fallback a slugify(name)
    for key in ("slug", "workspace_slug", "workspaceSlug"):
        if key in workspace_obj and workspace_obj[key]:
            return str(workspace_obj[key])
    # a volte la risposta annida l'oggetto
    ws = workspace_obj.get("workspace") if isinstance(workspace_obj, dict) else None
    if isinstance(ws, dict):
        for key in ("slug", "workspace_slug", "workspaceSlug"):
            if key in ws and ws[key]:
                return str(ws[key])
    return _slugify(workspace_name)

def _target_locations_for_embed(uploaded_docs: List[Dict[str, Any]], target_folder_name: str, verbose: bool=False) -> List[str]:
    targets: List[str] = []
    for d in uploaded_docs:
        loc = d.get("location") or d.get("new_location") or d.get("moved_location")
        if not loc:
            # Prova a derivare dal raw_location/basename
            raw = d.get("raw_location") or d.get("original_location") or ""
            base = Path(raw).name if raw else (d.get("title") or d.get("filename"))
            if base:
                loc = f"{target_folder_name}/{Path(base).with_suffix(Path(base).suffix + '.json') if not str(base).endswith('.json') else base}"
        if loc:
            # Normalizza separatori
            loc = str(loc).replace("\\", "/")
            # Assicurati che contenga il folder target
            if "/" in loc and not loc.startswith(f"{target_folder_name}/"):
                base = Path(loc).name
                loc = f"{target_folder_name}/{base}"
            targets.append(loc)
        elif verbose:
            print(f"   [EMBED WARN] impossibile determinare la location per il documento: {d}")
    # dedup
    seen = set()
    deduped = []
    for x in targets:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped

def ensure_workspace_and_embed_folder_docs(
    client: AnythingLLMClient,
    workspace_name: str,
    target_folder_name: str,
    uploaded_docs: List[Dict[str, Any]],
    cfg_workspace: Optional[dict] = None,
    verbose: bool=False,
) -> Dict[str, Any]:
    """
    - Trova o crea workspace (idempotente)
    - Per ogni documento in uploaded_docs, invia POST /api/v1/workspace/{slug}/update-embeddings con {"adds":[location]}
    - Niente polling (embed check rimosso su richiesta)
    """
    # 1) Trova workspace esistente
    existing = _find_workspace_by_name(client, workspace_name, verbose=verbose)
    if existing:
        slug = _extract_slug(existing, workspace_name)
        if verbose:
            print(f"   [WORKSPACE] Uso esistente: name='{workspace_name}', slug='{slug}'")
    else:
        # 2) Crea workspace
        created = _create_workspace(client, workspace_name, cfg_workspace, verbose=verbose)
        slug = _extract_slug(created, workspace_name)
        if verbose:
            print(f"   [WORKSPACE] Creato: name='{workspace_name}', slug='{slug}'")

    # 3) Prepara locations da embeddare
    targets = _target_locations_for_embed(uploaded_docs, target_folder_name, verbose=verbose)
    if verbose:
        print(f"   [EMBED] Trigger per {len(targets)} documenti.")

    # 4) Trigger embedding per ogni file (singolarmente)
    results = []
    for loc in targets:
        path = f"{client.api_base}/workspace/{slug}/update-embeddings"
        payload = {"adds": [loc]}
        if verbose:
            print(f"   [HTTP POST] POST {client.base_url.rstrip('/')}{path} adds=[{loc}]")
        try:
            res = client.post_json(path, payload)
            results.append({"location": loc, "status": "ok", "response": res})
        except Exception as e:
            results.append({"location": loc, "status": "error", "error": str(e)})
            if verbose:
                print(f"   [EMBED ERROR] {loc} -> {e}")

    return {
        "workspace": {
            "name": workspace_name,
            "slug": slug,
        },
        "embedded": results,
    }
