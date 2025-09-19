#!/bin/bash
# Script di esempio per utilizzare il RAG Verifier

# 1. Prima lista i workspace disponibili
echo "=== LISTING WORKSPACE DISPONIBILI ==="
python rag_verifier.py --config anythingllm_config_file.json --list-workspaces

echo -e "\n=== VERIFICA QUERY CIG SPECIFICO ==="
# 2. Verifica query per CIG specifico (849072933A dal tuo esempio)
python rag_verifier.py \
    --config anythingllm_config_file.json \
    --workspace "il-tuo-workspace-slug" \
    --queries "CIG 849072933A" "Codice CIG" "849072933A" \
    --limit 3 \
    --verbose

echo -e "\n=== VERIFICA QUERY MULTIPLE CON ANALISI ==="
# 3. Verifica query multiple con analisi sovrapposizioni
python rag_verifier.py \
    --config anythingllm_config_file.json \
    --workspace "il-tuo-workspace-slug" \
    --queries \
        "CIG" \
        "CUP" \
        "PNRR" \
        "D.Lgs 50/2016" \
        "D.Lgs 36/2023" \
        "criterio aggiudicazione" \
        "importo contratto" \
        "firme contratto" \
    --limit 5 \
    --analyze \
    --save "verifica_completa.json"

echo -e "\n=== VERIFICA QUERY PROBLEMATICHE ==="
# 4. Verifica delle query che spesso danno problemi
python rag_verifier.py \
    --config anythingllm_config_file.json \
    --workspace "il-tuo-workspace-slug" \
    --queries \
        "849072933A" \
        "CIG 849072933A" \
        "Codice Identificativo Gara 849072933A" \
        "procedimento gara" \
        "richiesta offerta" \
    --limit 3 \
    --analyze \
    --save "debug_cig_problema.json" \
    --verbose