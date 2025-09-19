#!/usr/bin/env python3
"""
RAG Chunk Verifier per AnythingLLM
Utility per verificare i chunk recuperati dalle query di ricerca
"""

import requests
import json
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys

class AnythingLLMRAGVerifier:
    def __init__(self, config_file: str = None, api_url: str = None, api_key: str = None):
        self.api_url = api_url
        self.api_key = api_key
        self.workspace_slug = None
        self.api_base = "/api/v1"
        self.timeout = 60
        
        # Carica configurazione da file JSON se fornito
        if config_file:
            self.load_config(config_file)
    
    def test_connection(self) -> bool:
        """Testa la connessione all'API AnythingLLM"""
        print("🔌 Test connessione API...")
        
        try:
            # Testa con endpoint workspaces
            response = self.list_workspaces()
            if response:
                print("✅ Connessione API funzionante")
                return True
            else:
                print("⚠️ Connessione API problematica - nessun workspace trovato")
                return False
                
        except Exception as e:
            print(f"❌ Test connessione fallito: {e}")
            return False
            
    def load_config(self, config_file: str):
        """Carica configurazione da file JSON specifico di AnythingLLM"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Estrae dalla struttura del tuo JSON
            server_config = config.get('server', {})
            auth_config = config.get('authentication', {})
            
            self.api_url = server_config.get('url', 'http://192.168.1.15:3001')
            self.api_base = server_config.get('api_base', '/api/v1')
            self.timeout = server_config.get('timeout', 60)
            self.api_key = auth_config.get('api_key')
            
            print(f"✅ Configurazione caricata: {config_file}")
            print(f"📍 API URL: {self.api_url}{self.api_base}")
            print(f"🔑 API Key: {self.api_key[:10]}..." if self.api_key else "❌ Nessuna API Key")
            
        except FileNotFoundError:
            print(f"❌ File di configurazione non trovato: {config_file}")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"❌ Errore nel parsing del JSON: {config_file}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Errore nel caricamento configurazione: {e}")
            sys.exit(1)
    
    def get_headers(self) -> Dict[str, str]:
        """Headers per le richieste API di AnythingLLM"""
        return {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
    
    def list_workspaces(self) -> List[Dict]:
        """Lista tutti i workspace disponibili"""
        url = f"{self.api_url}{self.api_base}/workspaces"
        
        try:
            response = requests.get(url, headers=self.get_headers(), timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            workspaces = data.get('workspaces', data.get('data', []))
            
            print(f"\n📋 WORKSPACE DISPONIBILI:")
            for ws in workspaces:
                slug = ws.get('slug', 'N/A')
                name = ws.get('name', 'N/A')
                print(f"   └─ {slug} ({name})")
            
            return workspaces
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore nel recupero workspace: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Errore JSON nel recupero workspace: {e}")
            return []
    
    def search_documents(self, query: str, workspace_slug: str = None, top_n: int = 4, score_threshold: float = 0.75) -> Dict[str, Any]:
        """
        Effettua ricerca documenti tramite API AnythingLLM usando vector-search endpoint
        """
        ws_slug = workspace_slug or self.workspace_slug
        if not ws_slug:
            raise ValueError("Workspace slug non specificato")
        
        # Endpoint corretto per vector search
        url = f"{self.api_url}{self.api_base}/workspace/{ws_slug}/vector-search"
        
        # Payload corretto per vector search
        payload = {
            'query': query,
            'topN': top_n,
            'scoreThreshold': score_threshold
        }
        
        # Header corretti per AnythingLLM
        headers = {
            'accept': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            
            # Debug della risposta per capire cosa succede
            print(f"🔧 DEBUG - Status Code: {response.status_code}")
            print(f"🔧 DEBUG - URL: {url}")
            print(f"🔧 DEBUG - Payload: {json.dumps(payload, indent=2)}")
            
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            
            print(f"🔧 DEBUG - Response Keys: {list(data.keys())}")
            print(f"🔧 DEBUG - Response Text (primi 300 char): {str(data)[:300]}...")
            
            return {
                'query': query,
                'raw_response': data,
                'chunks': self._extract_chunks(data),
                'sources': self._extract_sources(data),
                'metadata': self._extract_metadata(data),
                'search_params': {'topN': top_n, 'scoreThreshold': score_threshold}
            }
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Errore HTTP per query '{query}': {e}")
            # In caso di errore, stampa anche la risposta se disponibile
            if hasattr(e, 'response') and e.response is not None:
                print(f"🔧 Response Status: {e.response.status_code}")
                print(f"🔧 Response Text: {e.response.text[:500]}")
            
            return {
                'query': query,
                'error': f"HTTP Error: {e}",
                'chunks': [],
                'sources': [],
                'metadata': {},
                'search_params': {'topN': top_n, 'scoreThreshold': score_threshold}
            }
        except json.JSONDecodeError as e:
            print(f"❌ Errore JSON parsing per query '{query}': {e}")
            print(f"🔧 Response Text: {response.text[:500]}")
            return {
                'query': query,
                'error': f"JSON Error: {e}",
                'raw_text': response.text,
                'chunks': [],
                'sources': [],
                'metadata': {},
                'search_params': {'topN': top_n, 'scoreThreshold': score_threshold}
            }
        except Exception as e:
            print(f"❌ Errore generico per query '{query}': {e}")
            return {
                'query': query,
                'error': str(e),
                'chunks': [],
                'sources': [],
                'metadata': {},
                'search_params': {'topN': top_n, 'scoreThreshold': score_threshold}
            }
    
    def _extract_chunks(self, data: Dict) -> List[Dict]:
        """Estrae i chunk dalla risposta del vector-search endpoint"""
        chunks = []
        
        # Formato principale per /vector-search endpoint
        if isinstance(data, dict):
            # Se la risposta ha un array di risultati
            if 'results' in data and isinstance(data['results'], list):
                for result in data['results']:
                    chunks.append({
                        'text': result.get('text', result.get('content', result.get('metadata', {}).get('text', ''))),
                        'source': result.get('source', result.get('title', result.get('metadata', {}).get('title', result.get('metadata', {}).get('source', 'Unknown')))),
                        'score': result.get('score', result.get('similarity', result.get('distance', 0.0))),
                        'metadata': result.get('metadata', {}),
                        'page': result.get('metadata', {}).get('page', result.get('page', 'N/A')),
                        'chunk_id': result.get('id', result.get('chunk_id', 'N/A'))
                    })
            
            # Se la risposta è direttamente un array 
            elif 'data' in data and isinstance(data['data'], list):
                for item in data['data']:
                    chunks.append({
                        'text': item.get('text', item.get('content', '')),
                        'source': item.get('source', item.get('title', item.get('filename', 'Unknown'))),
                        'score': item.get('score', item.get('similarity', 0.0)),
                        'metadata': item.get('metadata', {}),
                        'page': item.get('page', 'N/A'),
                        'chunk_id': item.get('id', 'N/A')
                    })
            
            # Formato legacy: 'sources' array
            elif 'sources' in data and isinstance(data['sources'], list):
                for source in data['sources']:
                    chunks.append({
                        'text': source.get('text', source.get('content', '')),
                        'source': source.get('title', source.get('source', source.get('filename', 'Unknown'))),
                        'score': source.get('score', source.get('similarity', 1.0)),
                        'metadata': source.get('metadata', {}),
                        'page': source.get('page', 'N/A'),
                        'chunk_id': source.get('id', 'N/A')
                    })
        
        # Se la risposta è direttamente un array (possibile con vector-search)
        elif isinstance(data, list):
            for item in data:
                chunks.append({
                    'text': item.get('text', item.get('content', str(item))),
                    'source': item.get('source', item.get('filename', item.get('title', 'Unknown'))),
                    'score': item.get('score', item.get('similarity', 1.0)),
                    'metadata': item.get('metadata', {}),
                    'page': item.get('page', 'N/A'),
                    'chunk_id': item.get('id', 'N/A')
                })
        
        return chunks
    
    def _extract_sources(self, data: Dict) -> List[str]:
        """Estrae i nomi dei documenti fonte"""
        sources = set()
        
        # Estrae da vari formati possibili
        if 'sources' in data and isinstance(data['sources'], list):
            for source in data['sources']:
                sources.add(source.get('title', source.get('source', source.get('filename', 'Unknown'))))
        
        elif 'context' in data and isinstance(data['context'], list):
            for ctx in data['context']:
                sources.add(ctx.get('source', ctx.get('filename', 'Unknown')))
        
        # Se non trova fonti ma ci sono chunk estratti, prova a estrarle dai chunk
        chunks = self._extract_chunks(data)
        for chunk in chunks:
            if chunk.get('source') and chunk['source'] != 'Unknown':
                sources.add(chunk['source'])
        
        return list(sources)
    
    def _extract_metadata(self, data: Dict) -> Dict:
        """Estrae metadata dalla risposta"""
        metadata = {
            'total_chunks': len(self._extract_chunks(data)),
            'response_time': data.get('responseTime', 0),
            'model_used': data.get('model', 'Unknown'),
            'has_textResponse': 'textResponse' in data,
            'has_sources': 'sources' in data and bool(data['sources'])
        }
        
        # Aggiungi informazioni sui token se disponibili
        if 'usage' in data:
            metadata['usage'] = data['usage']
        
        return metadata
    
    def format_chunk_info(self, chunk: Dict, index: int) -> str:
        """Formatta le informazioni di un chunk per la visualizzazione"""
        
        text = chunk.get('text', chunk.get('content', ''))
        source = chunk.get('source', 'Sconosciuto')
        score = chunk.get('score', 0.0)
        metadata = chunk.get('metadata', {})
        page = chunk.get('page', 'N/A')
        chunk_id = chunk.get('chunk_id', 'N/A')
        
        # Limita il testo per leggibilità
        preview = text[:400] + "..." if len(text) > 400 else text
        
        # Cerca pattern CIG/CUP nel testo
        text_upper = text.upper()
        indicators = []
        
        if "CIG" in text_upper:
            # Cerca pattern CIG specifici
            import re
            cig_pattern = r'CIG[:\s]*([A-Z0-9]{10,})'
            cig_match = re.search(cig_pattern, text_upper)
            if cig_match:
                indicators.append(f"🔍 CIG:{cig_match.group(1)[:10]}")
            else:
                indicators.append("🔍 CIG")
        
        if "CUP" in text_upper:
            indicators.append("🏛️ CUP")
            
        if "PNRR" in text_upper:
            indicators.append("🇪🇺 PNRR")
            
        if any(term in text_upper for term in ["D.LGS", "D.L.", "DECRETO"]):
            indicators.append("📜 NORM")
        
        indicators_str = " ".join(indicators) if indicators else ""
        
        return f"""
📄 CHUNK #{index + 1} {indicators_str}
├─ 📁 Fonte: {source}
├─ 📊 Score: {score:.4f}
├─ 📄 Pagina: {page}
├─ 🆔 ID: {chunk_id}
├─ 📝 Lunghezza: {len(text)} caratteri
└─ 💬 Contenuto:
   {preview}
{'─' * 80}"""

    def verify_queries(self, queries: List[str], workspace_slug: str = None, top_n: int = 4, score_threshold: float = 0.75) -> Dict[str, Any]:
        """Verifica multiple query e restituisce risultati comparativi"""
        
        ws_slug = workspace_slug or self.workspace_slug
        if not ws_slug:
            print("❌ Workspace non specificato")
            return {}
        
        print(f"\n🔍 VERIFICA RAG CHUNKS - AnythingLLM Vector Search")
        print(f"📅 Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 Server: {self.api_url}")
        print(f"🏢 Workspace: {ws_slug}")
        print(f"📊 TopN per query: {top_n}")
        print(f"🎯 Score threshold: {score_threshold}")
        print("=" * 80)
        
        all_results = {}
        
        for i, query in enumerate(queries, 1):
            print(f"\n🎯 QUERY {i}/{len(queries)}: '{query}'")
            print("-" * 60)
            
            result = self.search_documents(query, ws_slug, top_n, score_threshold)
            chunks = result['chunks']
            sources = result['sources']
            metadata = result['metadata']
            
            all_results[query] = result
            
            if 'error' in result:
                print(f"❌ Errore: {result['error']}")
                continue
            
            if chunks:
                print(f"✅ Trovati {len(chunks)} chunk(s) da {len(sources)} documento(i)")
                print(f"📚 Fonti: {', '.join(sources)}")
                
                for j, chunk in enumerate(chunks):
                    print(self.format_chunk_info(chunk, j))
            else:
                print("❌ Nessun chunk trovato")
                
                # Mostra la risposta grezza per debug se non ci sono chunk
                if 'raw_response' in result:
                    print("\n🔧 DEBUG - Risposta grezza:")
                    print(json.dumps(result['raw_response'], indent=2, ensure_ascii=False)[:500] + "...")
            
            print("-" * 60)
        
        return all_results
    
    def analyze_overlap(self, results: Dict[str, List]) -> None:
        """Analizza sovrapposizioni tra risultati di query diverse"""
        
        print(f"\n📈 ANALISI SOVRAPPOSIZIONI")
        print("=" * 80)
        
        queries = list(results.keys())
        
        if len(queries) < 2:
            print("⚠️  Servono almeno 2 query per l'analisi sovrapposizioni")
            return
        
        for i, query1 in enumerate(queries):
            for query2 in queries[i+1:]:
                chunks1 = results[query1]
                chunks2 = results[query2]
                
                # Trova chunk in comune (basandosi su similarità del testo)
                common_chunks = []
                for chunk1 in chunks1:
                    text1 = chunk1.get('text', '').lower()
                    source1 = chunk1.get('source', '')
                    
                    for chunk2 in chunks2:
                        text2 = chunk2.get('text', '').lower()
                        source2 = chunk2.get('source', '')
                        
                        # Considera comuni se stesso testo o stessa fonte con testo simile
                        if (text1 == text2) or (source1 == source2 and len(text1) > 50 and text1[:50] == text2[:50]):
                            common_chunks.append({
                                'source': source1,
                                'text_preview': text1[:100] + "..." if len(text1) > 100 else text1
                            })
                
                overlap_rate = len(common_chunks) / max(len(chunks1), len(chunks2), 1) * 100
                
                print(f"🔗 '{query1}' ↔ '{query2}'")
                print(f"   ├─ Query 1: {len(chunks1)} chunk(s)")
                print(f"   ├─ Query 2: {len(chunks2)} chunk(s)")
                print(f"   ├─ Comuni: {len(common_chunks)} chunk(s)")
                print(f"   └─ Tasso sovrapposizione: {overlap_rate:.1f}%")
                
                if common_chunks and len(common_chunks) <= 3:
                    print(f"   📝 Chunk comuni:")
                    for j, chunk in enumerate(common_chunks[:3], 1):
                        print(f"      {j}. {chunk['source']}: {chunk['text_preview']}")
                print()

    def print_summary(self, results: Dict[str, Any]) -> None:
        """Stampa riepilogo dei risultati"""
        
        print(f"\n📊 RIEPILOGO RISULTATI")
        print("=" * 80)
        
        total_queries = len(results)
        queries_with_results = sum(1 for r in results.values() if r.get('chunks'))
        total_chunks = sum(len(r.get('chunks', [])) for r in results.values())
        unique_sources = set()
        
        # Estrai parametri di ricerca dalla prima query
        first_result = next(iter(results.values()), {})
        search_params = first_result.get('search_params', {})
        
        for result in results.values():
            unique_sources.update(result.get('sources', []))
        
        print(f"🎯 Query totali: {total_queries}")
        print(f"✅ Query con risultati: {queries_with_results}")
        print(f"📄 Chunk totali recuperati: {total_chunks}")
        print(f"📚 Documenti unici coinvolti: {len(unique_sources)}")
        
        # Mostra parametri di ricerca usati
        if search_params:
            print(f"⚙️  Parametri ricerca:")
            print(f"   ├─ TopN: {search_params.get('topN', 'N/A')}")
            print(f"   └─ Score threshold: {search_params.get('scoreThreshold', 'N/A')}")
        
        if unique_sources:
            print(f"\n📋 Documenti fonte:")
            for source in sorted(unique_sources):
                print(f"   └─ {source}")
        
        # Statistiche per query con range di score
        print(f"\n📈 Dettagli per query:")
        for query, result in results.items():
            chunks = result.get('chunks', [])
            sources = result.get('sources', [])
            error = result.get('error')
            
            if error:
                print(f"   ❌ '{query}': ERRORE - {error}")
            elif chunks:
                scores = [chunk.get('score', 0) for chunk in chunks]
                min_score = min(scores) if scores else 0
                max_score = max(scores) if scores else 0
                print(f"   📊 '{query}': {len(chunks)} chunk(s) da {len(sources)} doc - Score range: [{min_score:.3f}, {max_score:.3f}]")
            else:
                print(f"   ⚪ '{query}': Nessun risultato")
        
        # Suggerimenti se pochi risultati
        if queries_with_results < total_queries * 0.5:
            print(f"\n💡 SUGGERIMENTI:")
            print(f"   └─ Pochi risultati trovati. Prova:")
            print(f"      ├─ Ridurre --threshold (es. 0.3 o 0.1)")
            print(f"      ├─ Aumentare --topn (es. 10 o 15)")
            print(f"      └─ Usare query più semplici (parole singole)")
        
        if total_chunks == 0:
            print(f"\n⚠️  NESSUN CHUNK TROVATO:")
            print(f"   ├─ Verifica che i documenti siano stati indicizzati")
            print(f"   ├─ Controlla il nome del workspace")
            print(f"   └─ Prova threshold più basso (--threshold 0.1)")

    def save_results(self, results: Dict, filename: str = None):
        """Salva risultati in file JSON"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            workspace = self.workspace_slug or "unknown"
            filename = f"rag_verification_{workspace}_{timestamp}.json"
        
        # Prepara dati per il salvataggio (rimuove oggetti non serializzabili)
        save_data = {}
        for query, result in results.items():
            save_data[query] = {
                'query': query,
                'chunks_count': len(result.get('chunks', [])),
                'chunks': result.get('chunks', []),
                'sources': result.get('sources', []),
                'metadata': result.get('metadata', {}),
                'error': result.get('error')
            }
        
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'workspace': self.workspace_slug,
            'api_url': self.api_url,
            'total_queries': len(results),
            'results': save_data
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Risultati salvati in: {filename}")
            print(f"📦 Dimensione file: {len(json.dumps(output_data))} caratteri")
        except Exception as e:
            print(f"❌ Errore nel salvataggio: {e}")

def main():
    parser = argparse.ArgumentParser(
        description='Verifica chunk RAG di AnythingLLM per documenti di gara',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi d'uso:

1. Test connessione:
   python rag_verifier.py --config anythingllm_config_file.json --test-connection

2. Lista workspace disponibili:
   python rag_verifier.py --config anythingllm_config_file.json --list-workspaces

3. Verifica query specifiche:
   python rag_verifier.py --config anythingllm_config_file.json --workspace "prj_39450-originale" \\
   --queries "CIG 849072933A" "Codice CIG" "849072933A" --topn 5 --threshold 0.7

4. Verifica con parametri personalizzati:
   python rag_verifier.py --config anythingllm_config_file.json --workspace "prj_39450-originale" \\
   --queries "CIG" "CUP" "PNRR" --topn 10 --threshold 0.5 --analyze --save results.json
        """)
    
    parser.add_argument('--config', '-c', required=True,
                       help='File JSON di configurazione AnythingLLM')
    parser.add_argument('--workspace', '-w',
                       help='Slug del workspace da interrogare')
    parser.add_argument('--list-workspaces', action='store_true',
                       help='Lista tutti i workspace disponibili')
    parser.add_argument('--test-connection', action='store_true',
                       help='Testa la connessione all\'API AnythingLLM')
    parser.add_argument('--queries', '-q', nargs='+',
                       help='Lista di query da testare')
    parser.add_argument('--topn', '-n', type=int, default=4,
                       help='Numero massimo di chunk per query (default: 4)')
    parser.add_argument('--threshold', '-t', type=float, default=0.75,
                       help='Soglia di score per i risultati (default: 0.75)')
    parser.add_argument('--save', '-s', nargs='?', const='auto',
                       help='Salva risultati in file JSON (opzionale: nome file)')
    parser.add_argument('--analyze', '-a', action='store_true',
                       help='Esegui analisi sovrapposizioni tra query')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Output dettagliato per debug')
    
    args = parser.parse_args()
    
    # Inizializza verifier
    try:
        verifier = AnythingLLMRAGVerifier(config_file=args.config)
    except Exception as e:
        print(f"❌ Errore nell'inizializzazione: {e}")
        sys.exit(1)
    
    # Test connessione se richiesto
    if args.test_connection:
        success = verifier.test_connection()
        if not success:
            print("💡 Controlla URL, API key e che il servizio AnythingLLM sia attivo")
        return
    
    # Imposta workspace se fornito da argomento
    if args.workspace:
        verifier.workspace_slug = args.workspace
    
    # Lista workspace se richiesto
    if args.list_workspaces:
        workspaces = verifier.list_workspaces()
        if not workspaces:
            print("❌ Nessun workspace trovato o errore di connessione")
            print("💡 Usa --test-connection per verificare la connessione")
        return
    
    # Verifica che abbiamo le query e il workspace
    if not args.queries:
        print("❌ Specifica almeno una query con --queries")
        parser.print_help()
        return
    
    if not verifier.workspace_slug:
        print("❌ Specifica un workspace con --workspace")
        print("💡 Usa --list-workspaces per vedere i workspace disponibili")
        return
    
    # Verifica configurazione
    if not all([verifier.api_url, verifier.api_key]):
        print("❌ Configurazione incompleta. Controlla il file JSON.")
        return
    
    # Esegui verifica query
    print(f"🚀 Avvio verifica con {len(args.queries)} query...")
    print(f"🎯 Parametri: TopN={args.topn}, Threshold={args.threshold}")
    
    try:
        results = verifier.verify_queries(
            args.queries, 
            verifier.workspace_slug, 
            args.topn,
            args.threshold
        )
        
        if not results:
            print("❌ Nessun risultato ottenuto")
            return
        
        # Analisi sovrapposizioni se richiesta
        if args.analyze:
            verifier.analyze_overlap({k: v['chunks'] for k, v in results.items()})
        
        # Riepilogo finale
        verifier.print_summary(results)
        
        # Salvataggio se richiesto
        if args.save:
            filename = args.save if args.save != 'auto' else None
            verifier.save_results(results, filename)
            
    except Exception as e:
        print(f"❌ Errore durante l'esecuzione: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()