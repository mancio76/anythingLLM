#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional

try:
    import pandas as pd
except ImportError:
    print("Questo script richiede pandas: pip install pandas")
    sys.exit(1)

# ------------------------------
# Utilità
# ------------------------------

def read_config(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Fallback sicuri
    data.setdefault("csv_to_yaml", {})
    c = data["csv_to_yaml"]
    c.setdefault("output_dir", "prompts_anythingllm")
    c.setdefault("filename_pattern", "{index:03d}-{slug}.yaml")
    c.setdefault("question_header_candidates", ["Domanda", "Domande", "Question", "Q"])
    c.setdefault("answers_header_candidates", ["Risposte", "Answer", "Answers", "A"])
    c.setdefault("answers_split_separators", [";", "|", "\n", "•", " - "])
    c.setdefault("min_token_len", 1)
    c.setdefault("max_expected_items", 12)
    c.setdefault("slug_maxlen", 80)
    c.setdefault("slug_separator", "_")
    c.setdefault("collapse_spaces", True)
    return data

def strip_accents(s: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))

def normalize_header(s: str) -> str:
    s = s or ""
    s = strip_accents(s)
    s = s.lower()
    # togliamo punteggiatura comune e due punti
    s = re.sub(r"[:;,.!?\-–—/\\]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def sanitize_text_for_yaml(s: str) -> str:
    if s is None:
        return ""
    # Evita problemi YAML rimuovendo i “:”
    s = s.replace(":", " - ")
    # Normalizza spazi
    s = re.sub(r"\s+", " ", s).strip()
    return s

def slugify(s: str, maxlen: int, sep: str, collapse_spaces: bool = True) -> str:
    s = strip_accents(s)
    s = s.replace(":", " ")
    s = s.replace("/", " ")
    s = s.replace("\\", " ")
    s = s.replace("|", " ")
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    if collapse_spaces:
        s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", sep)
    if len(s) > maxlen:
        s = s[:maxlen].rstrip(sep)
    return s or "item"

def ensure_unique_path(base_dir: Path, base_name: str) -> Path:
    """
    Rende il filename unico aggiungendo un progressivo _01, _02... prima dell'estensione.
    """
    p = base_dir / base_name
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    i = 1
    while True:
        candidate = base_dir / f"{stem}_{i:02d}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1

def split_answers(raw: str, seps: List[str], min_token_len: int, max_expected: int) -> List[str]:
    if not raw:
        return []
    # Costruisci regex dagli separators (escape per sicurezza), ordinati per lunghezza desc
    seps_sorted = sorted(seps, key=len, reverse=True)
    rx = "|".join(re.escape(s) for s in seps_sorted)
    parts = re.split(rx, raw)
    cleaned = []
    for p in parts:
        t = sanitize_text_for_yaml(p)
        if len(t) >= min_token_len:
            cleaned.append(t)
        if len(cleaned) >= max_expected:
            break
    # rimuovi duplicati preservando ordine
    seen = set()
    uniq = []
    for a in cleaned:
        if a not in seen:
            uniq.append(a)
            seen.add(a)
    return uniq

def detect_columns(df: pd.DataFrame, q_candidates: List[str], a_candidates: List[str]) -> Tuple[str, str]:
    """
    Prova a mappare le colonne della tabella usando le liste dal config.
    Ritorna (question_col, answers_col). Solleva ValueError se non trova corrispondenze.
    """
    norm_cols = {col: normalize_header(str(col)) for col in df.columns}
    norm_to_original = {v: k for k, v in norm_cols.items()}

    def best_match(cands: List[str]) -> Optional[str]:
        norm_cands = [normalize_header(c) for c in cands]
        # match esatto
        for nc in norm_cands:
            if nc in norm_to_original:
                return norm_to_original[nc]
        # match parziale (startswith/contains)
        for nc in norm_cands:
            for col_norm, original in norm_cols.items():
                # col_norm qui è già l'original key, fix:
                pass
        # correggo: dobbiamo iterare sugli items
        for nc in norm_cands:
            for orig, nrm in norm_cols.items():
                if nrm.startswith(nc) or nc in nrm:
                    return orig
        return None

    q_col = best_match(q_candidates)
    a_col = best_match(a_candidates)

    if not q_col or not a_col:
        raise ValueError(
            f"Impossibile individuare le colonne. Trovate: {list(df.columns)} | "
            f"Attese (question any of): {q_candidates} | (answers any of): {a_candidates}"
        )
    return q_col, a_col

def write_yaml(path: Path, question: str, answers: List[str]) -> None:
    # YAML minimale per AnythingLLM "aprompts"
    # Formato esempi:
    # ---
    # question: "...."
    # expected_answers:
    #   - "..."
    #   - "..."
    # ---
    lines = ["---", f'question: "{question}"', "expected_answers:"]
    for a in answers:
        lines.append(f'  - "{a}"')
    lines.append("---\n")
    path.write_text("\n".join(lines), encoding="utf-8")

# ------------------------------
# Main
# ------------------------------

def load_table(input_path: Path) -> pd.DataFrame:
    if input_path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(input_path)
    # Default CSV con autodetect delimitatore tramite pandas
    return pd.read_csv(input_path)

def main():
    ap = argparse.ArgumentParser(description="Convertitore CSV/XLS → YAML per AnythingLLM (config-driven).")
    ap.add_argument("input", help="File CSV/XLSX/XLS con domande e risposte.")
    ap.add_argument("--config", default="anythingllm_config_file.json", help="File di configurazione JSON.")
    ap.add_argument("--verbose", action="store_true", help="Log a schermo.")
    args = ap.parse_args()

    cfg = read_config(args.config)
    c_csv = cfg["csv_to_yaml"]

    out_dir = Path(c_csv["output_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    logging.info(f"Config: {args.config}")
    logging.info(f"Output dir: {out_dir}")

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"File non trovato: {input_path}")
        sys.exit(1)

    # Carica tabella
    df = load_table(input_path)

    # Individua colonne in base a config
    q_col, a_col = detect_columns(
        df,
        c_csv["question_header_candidates"],
        c_csv["answers_header_candidates"],
    )
    logging.info(f"Colonna Domande: {q_col} | Colonna Risposte: {a_col}")

    # Preparazione parametri
    seps = c_csv["answers_split_separators"]
    min_token_len = int(c_csv["min_token_len"])
    max_expected = int(c_csv["max_expected_items"])
    slug_maxlen = int(c_csv["slug_maxlen"])
    slug_sep = str(c_csv["slug_separator"])
    collapse_spaces = bool(c_csv["collapse_spaces"])
    filename_pattern = str(c_csv["filename_pattern"])

    # Generazione file
    counter = Counter()
    total = 0
    written = 0

    for idx, row in df.iterrows():
        raw_q = str(row.get(q_col, "") or "")
        raw_a = str(row.get(a_col, "") or "")

        q = sanitize_text_for_yaml(raw_q)
        if not q:
            continue

        answers = split_answers(raw_a, seps, min_token_len, max_expected)

        slug = slugify(q, slug_maxlen, slug_sep, collapse_spaces)
        counter[slug] += 1
        # Preambolo progressivo nel filename è gestito da ensure_unique_path,
        # ma manteniamo il pattern (es. {index}-{slug})
        file_name = filename_pattern.format(index=idx + 1, slug=slug)
        # doppia sicurezza: se duplichiamo, ensure_unique_path appende _NN
        target = ensure_unique_path(out_dir, file_name)

        write_yaml(target, q, answers)
        written += 1
        total += 1
        if args.verbose:
            logging.info(f"📝 {target.name} (answers: {len(answers)})")
    print("============================================================")
    print("✅ CONVERSIONE COMPLETATA")
    print("============================================================")
    print(f"Input:   {input_path}")
    print(f"Config:  {args.config}")
    print(f"Output:  {out_dir}")
    print(f"Righe totali lette: {len(df)}")
    print(f"File YAML scritti:  {written}")

if __name__ == "__main__":
    main()
