
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main program for ZIP -> AnythingLLM pipeline (config structure preserved).

Pipeline aggiornata:
1) Unzip ZIP.
2) Upload TUTTI i file nel folder di default "custom-documents".
3) Crea il folder di destinazione.
4) Sposta i file dal default al folder di destinazione.
5) Crea/usa workspace e lancia embedding SINGOLO per ogni file spostato, con polling su GET workspace.

Logging meccanismo rimane esterno via requests_http_logger.py (unchanged).
"""
import argparse
import json
import sys
from pathlib import Path

# --- Keep external HTTP logging untouched ---
try:
    import requests_http_logger  # DO NOT MODIFY THIS FILE
except Exception as e:
    print("⚠️  Impossibile importare requests_http_logger.py:", e, file=sys.stderr)

# Internal modules (this project)
from gare_unzip import extract_zip
from gare_anythingllm_upload import (
    AnythingLLMClient,
    create_folder_if_needed,
    upload_files_to_default,
    move_files_to_folder,
    DEFAULT_API_BASE,
)
from gare_workspace_embed import (
    ensure_workspace_and_embed_folder_docs
)

BANNER = """\
======================================================================
🔧 GARE ZIP UPLOADER - VERSIONE MODULARE
   🧩 Split in 4 file per manutenzione semplificata
======================================================================
"""

def load_config(path: Path) -> dict:
    """
    Carica la configurazione SENZA modificarne la struttura.
    Ritorna un dict normalizzato solo per i campi operativi interni, mantenendo l'originale sotto 'raw'.
    """
    with path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "server" not in cfg or "authentication" not in cfg:
        raise ValueError("Config mancante delle sezioni obbligatorie 'server' o 'authentication'")

    server_url = cfg["server"].get("url")
    api_key = cfg["authentication"].get("api_key")

    if not server_url or not api_key:
        raise ValueError("Config mancante: server.url o authentication.api_key")

    normalized = {
        "server_url": server_url,
        "api_key": api_key,
        "timeout_seconds": cfg["server"].get("timeout", 60),
        "max_retries": cfg["server"].get("max_retries", 3),
        "api_base": cfg["server"].get("api_base", DEFAULT_API_BASE),
        "raw": cfg
    }
    return normalized

def main(argv=None):
    print(BANNER)
    parser = argparse.ArgumentParser(
        description="Carica documenti da uno ZIP in AnythingLLM (cartella + workspace + embedding)."
    )
    parser.add_argument("zipfile", help="Percorso al file ZIP di gara")
    parser.add_argument("--config", default="anythingllm_config_file.json", help="File di configurazione JSON (default: anythingllm_config_file.json)")
    parser.add_argument("--workspace", help="Nome workspace da creare/riutilizzare (default: nome ZIP senza estensione)")
    parser.add_argument("--folder", help="Nome folder di destinazione su AnythingLLM (default: uguale al workspace)")
    parser.add_argument("--verbose", action="store_true", help="Abilita log verbosi lato client")
    args = parser.parse_args(argv)

    zip_path = Path(args.zipfile).expanduser().resolve()
    if not zip_path.exists():
        print(f"❌ ZIP non trovato: {zip_path}", file=sys.stderr)
        return 2

    cfg_path = Path(args.config).expanduser().resolve()
    try:
        cfg = load_config(cfg_path)
    except Exception as e:
        print(f"❌ Errore caricando config '{cfg_path}': {e}", file=sys.stderr)
        return 3

    # Derive names
    workspace_name = args.workspace or zip_path.stem
    folder_name = args.folder or workspace_name

    print(f"📁 File ZIP: {zip_path.name}")
    print(f"📋 Config:   {cfg_path.name}")
    print(f"🗂️  Folder:   {folder_name}")
    print(f"🏷️  Workspace:{workspace_name}")
    print(f"🌐 Server:   {cfg['server_url']}")
    print(f"🔗 API base: {cfg['api_base']}")
    if args.verbose:
        print("🔍 Modalità debug attivata")

    # Build API client (session & base URL come from config)
    client = AnythingLLMClient(
        base_url=cfg["server_url"],
        api_key=cfg["api_key"],
        timeout=cfg.get("timeout_seconds", 60),
        verbose=args.verbose,
        api_base=cfg["api_base"],
    )

    # 1) Unzip
    extract_dir = zip_path.parent / f".unzipped_{zip_path.stem}"
    extract_dir.mkdir(exist_ok=True)
    extracted_files = extract_zip(zip_path, extract_dir, verbose=args.verbose)
    if not extracted_files:
        print("❌ Nessun file estratto. Interrompo.", file=sys.stderr)
        return 4
    print(f"✅ Estratti {len(extracted_files)} file in: {extract_dir}")

    # 2) Upload nel folder di default 'custom-documents'
    uploaded_docs = upload_files_to_default(client, extracted_files, verbose=args.verbose)

    # 3) Crea folder di destinazione (idempotente)
    create_folder_if_needed(client, folder_name)

    # 4) Sposta i file nel folder di destinazione
    moved_docs = move_files_to_folder(client, folder_name, uploaded_docs, verbose=args.verbose)

    # 5) Workspace + embedding singolo per file con polling
    result = ensure_workspace_and_embed_folder_docs(
        client=client,
        workspace_name=workspace_name,
        target_folder_name=folder_name,
        uploaded_docs=moved_docs,
        cfg_workspace=cfg["raw"].get("workspace"),
        verbose=args.verbose,
    )

    print("✅ Operazione completata.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
