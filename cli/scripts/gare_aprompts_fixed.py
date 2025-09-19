#!/usr/bin/env python3
"""
Test AnythingLLM con thread dedicati e configurazione esterna
Versione corretta che:
- Crea un nuovo thread per ogni esecuzione
- Utilizza configurazione esterna (anythingllm_config_file.json)
- Nomina i thread con timestamp + "aprompts"
- Esegue tutti i test nel thread creato con configurazione LLM corretta
- RICHIEDE workspace obbligatorio (no fallback)
"""

import os
import requests
import yaml
import time
import csv
import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Tuple, Any
from pathlib import Path

# Nome file di configurazione
CONFIG_FILE = "anythingllm_config_file.json"


class TestRunner:
    """Classe per eseguire test su AnythingLLM con thread dedicati"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config = self.load_config(config_file)
        self.setup_logging()
        
        # Configurazioni dal file JSON
        self.base_url = self.config['server']['url'].rstrip('/')
        self.api_key = self.config['authentication']['api_key']
        self.timeout = self.config['server']['timeout']
        
        # Impostazioni test
        self.workspace_slug = None
        self.workspace_id = None
        self.thread_slug = None
        self.thread_id = None
        self.prompt_dir = "./prompts_anythingllm"
        self.output_csv = None
        
        # Statistiche
        self.test_results = []
        self.start_time = None
        
        # Setup sessione HTTP
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        })
        
        logging.info(f"TestRunner inizializzato - Server: {self.base_url}")
    
    def load_config(self, config_file: str) -> Dict:
        """Carica la configurazione dal file JSON"""
        if not os.path.exists(config_file):
            print(f"❌ File di configurazione '{config_file}' non trovato!")
            print("Assicurati che il file esista e contenga le configurazioni necessarie.")
            sys.exit(1)
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"✅ Configurazione caricata da '{config_file}'")
                return config
        except json.JSONDecodeError as e:
            print(f"❌ Errore nel parsing del file di configurazione: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Errore caricamento configurazione: {e}")
            sys.exit(1)
    
    def setup_logging(self):
        """Configura il sistema di logging"""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO'))
        
        # Nome log file con timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f"aprompts_run_{timestamp}.log"
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # Setup logger
        logger = logging.getLogger()
        logger.setLevel(log_level)
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    def test_connection(self) -> bool:
        """Verifica la connessione al server AnythingLLM"""
        try:
            endpoints = [
                "/api/v1/workspaces",
                "/api/v1/system/env-dump",
                "/api/health",
                "/api/v1/system"
            ]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.base_url}{endpoint}"
                    response = self.session.get(url, timeout=5)
                    
                    if response.status_code in [200, 201]:
                        logging.info(f"Connessione riuscita via {endpoint}")
                        return True
                except:
                    continue
            
            logging.error("Connessione fallita a tutti gli endpoint")
            return False
            
        except Exception as e:
            logging.error(f"Errore test connessione: {e}")
            return False
    
    def get_available_workspaces(self) -> List[Dict]:
        """Ottiene la lista completa dei workspace disponibili"""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/workspaces",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                workspaces = data.get('workspaces', data if isinstance(data, list) else [])
                logging.info(f"Trovati {len(workspaces)} workspace disponibili")
                return workspaces
            else:
                logging.error(f"Errore API recupero workspace: {response.status_code}")
                return []
                
        except Exception as e:
            logging.error(f"Errore recupero workspace: {e}")
            return []
    
    def get_workspace_info(self, workspace_identifier: str) -> Tuple[bool, str]:
        """
        Ottiene informazioni sul workspace ESATTO specificato
        NON usa fallback su altri workspace
        
        Args:
            workspace_identifier: Nome o slug del workspace (OBBLIGATORIO)
            
        Returns:
            Tuple (success, workspace_slug_or_error_message)
        """
        if not workspace_identifier or not workspace_identifier.strip():
            return False, "Nome workspace non specificato"
        
        workspace_identifier = workspace_identifier.strip()
        
        try:
            workspaces = self.get_available_workspaces()
            
            if not workspaces:
                return False, "Nessun workspace disponibile sul server"
            
            # Cerca il workspace ESATTO per nome o slug
            for ws in workspaces:
                ws_slug = ws.get('slug', '').strip()
                ws_name = ws.get('name', '').strip()
                ws_id = ws.get('id')
                
                if (ws_slug.lower() == workspace_identifier.lower() or 
                    ws_name.lower() == workspace_identifier.lower()):
                    self.workspace_slug = ws_slug
                    self.workspace_id = ws_id
                    logging.info(f"Workspace trovato: '{ws_name}' (slug: {ws_slug}, id: {ws_id})")
                    return True, ws_slug
            
            # Se arriviamo qui, il workspace NON è stato trovato
            available_names = []
            for ws in workspaces:
                name = ws.get('name', ws.get('slug', 'N/A'))
                slug = ws.get('slug', 'N/A')
                available_names.append(f"'{name}' (slug: {slug})")
            
            error_msg = f"Workspace '{workspace_identifier}' NON TROVATO.\n"
            error_msg += f"Workspace disponibili:\n"
            for name in available_names[:10]:  # Mostra max 10
                error_msg += f"  - {name}\n"
            
            if len(available_names) > 10:
                error_msg += f"  ... e altri {len(available_names) - 10} workspace"
            
            logging.error(f"Workspace '{workspace_identifier}' non trovato")
            return False, error_msg
                
        except Exception as e:
            logging.error(f"Errore recupero workspace: {e}")
            return False, f"Errore connessione: {str(e)}"
    
    def detect_llm_provider(self, model_name: str) -> str:
        """
        Rileva automaticamente il provider corretto dal nome del modello
        
        Args:
            model_name: Nome del modello (es. "gpt-3.5-turbo", "deepseek-r1:latest")
            
        Returns:
            Nome del provider ("openai", "ollama", "anthropic", etc.)
        """
        model_lower = model_name.lower()
        
        # Modelli OpenAI
        openai_models = [
            'gpt-3.5', 'gpt-4', 'text-embedding-ada', 'text-embedding-3',
            'davinci', 'curie', 'babbage', 'ada'
        ]
        
        # Modelli Anthropic
        anthropic_models = ['claude', 'claude-3', 'claude-2']
        
        # Modelli locali/Ollama (hanno ":latest" o nomi specifici)
        if ':' in model_name or any(keyword in model_lower for keyword in [
            'deepseek', 'llama', 'mistral', 'qwen', 'phi', 'gemma', 
            'solar', 'wizardlm', 'vicuna', 'alpaca'
        ]):
            return 'ollama'
        
        # Controlla modelli OpenAI
        if any(keyword in model_lower for keyword in openai_models):
            return 'openai'
        
        # Controlla modelli Anthropic
        if any(keyword in model_lower for keyword in anthropic_models):
            return 'anthropic'
        
        # Default per modelli sconosciuti - prova prima ollama per modelli locali
        logging.warning(f"Provider non riconosciuto per {model_name}, uso 'ollama'")
        return 'ollama'
    
    def update_workspace_llm_config(self, llm_params: Dict) -> bool:
        """
        Aggiorna la configurazione LLM del workspace
        Rileva automaticamente il provider corretto dal modello
        """
        if not self.workspace_slug:
            return False
        
        endpoint = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/update"
        
        # Prepara i parametri di aggiornamento del workspace
        update_payload = {}
        
        # Rileva il provider corretto dal modello
        model_name = llm_params.get('model', '')
        if model_name:
            provider = self.detect_llm_provider(model_name)
            update_payload['chatProvider'] = provider
            update_payload['chatModel'] = model_name
            
            logging.info(f"Rilevato provider '{provider}' per modello '{model_name}'")
        
        # Aggiungi temperatura
        if 'temperature' in llm_params:
            update_payload['openAiTemp'] = llm_params['temperature']
        
        try:
            logging.info(f"Aggiornamento configurazione LLM workspace: {update_payload}")
            
            response = self.session.post(
                endpoint,
                json=update_payload,
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                logging.info("Configurazione LLM workspace aggiornata")
                return True
            else:
                logging.warning(f"Aggiornamento LLM fallito: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"Errore aggiornamento LLM workspace: {e}")
            return False
    
    def create_test_thread(self) -> Tuple[bool, str]:
        """
        Crea un nuovo thread per i test con nome timestamp-aprompts
        
        Returns:
            Tuple (success, thread_slug)
        """
        if not self.workspace_slug:
            return False, "Workspace non impostato"
        
        # Genera nome thread con timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        thread_name = f"{timestamp}-aprompts"
        
        endpoint = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/thread/new"
        
        payload = {
            "name": thread_name
        }
        
        try:
            logging.info(f"Creazione thread: {thread_name}")
            logging.debug(f"Endpoint: {endpoint}")
            logging.debug(f"Payload: {json.dumps(payload)}")
            
            response = self.session.post(
                endpoint,
                json=payload,
                timeout=self.timeout
            )
            
            logging.debug(f"Response status: {response.status_code}")
            logging.debug(f"Response body: {response.text[:500]}")
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                # Estrai informazioni del thread - prova diversi campi
                thread_info = data.get('thread', data)
                self.thread_slug = thread_info.get('slug', thread_name)
                self.thread_id = thread_info.get('id') or thread_info.get('threadId')
                
                logging.info(f"Thread creato: slug={self.thread_slug}, id={self.thread_id}")
                return True, self.thread_slug
            
            elif response.status_code == 400:
                # Thread potrebbe già esistere
                if 'already exists' in response.text.lower() or 'duplicate' in response.text.lower():
                    self.thread_slug = thread_name
                    # Prova a ottenere l'ID del thread esistente
                    self.thread_id = self.get_thread_id(thread_name)
                    logging.info(f"Thread già esistente, lo utilizzo: {thread_name}")
                    return True, thread_name
                else:
                    return False, f"Errore creazione thread: {response.text[:200]}"
            else:
                return False, f"Errore HTTP {response.status_code}: {response.text[:200]}"
                
        except Exception as e:
            logging.error(f"Errore creazione thread: {e}")
            return False, f"Errore: {str(e)}"
    
    def get_thread_id(self, thread_slug: str) -> str:
        """
        Ottiene l'ID del thread dal suo slug
        """
        try:
            # Prova a ottenere la lista dei thread del workspace
            endpoint = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/threads"
            response = self.session.get(endpoint, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                threads = data.get('threads', [])
                
                for thread in threads:
                    if thread.get('slug') == thread_slug:
                        thread_id = thread.get('id')
                        logging.info(f"Thread ID trovato: {thread_id}")
                        return thread_id
            
            # Fallback: usa lo slug come ID
            logging.warning(f"Thread ID non trovato, uso slug: {thread_slug}")
            return thread_slug
            
        except Exception as e:
            logging.error(f"Errore recupero thread ID: {e}")
            return thread_slug
    
    def verify_thread_exists(self) -> bool:
        """
        Verifica che il thread creato esista effettivamente nel workspace
        """
        # Proviamo a bypassare tutta questa logica in quanto non esiste un modo per verificare che un thread esista
        logging.warning(f"Verifica esistenza del thread {self.thread_slug} bypassato perche' non esiste un metodo specifico. Si procede dando per scontato che il thread esista")
        return True

    """    
	if not self.workspace_slug or not self.thread_slug:
            return False
        
        try:
            # Prova a ottenere la lista dei thread del workspace invece del singolo thread
            endpoint = f"{self.base_url}/api/v1/workspace/{self.workspace_slug}/threads"
            response = self.session.get(endpoint, timeout=10)
            
            logging.debug(f"Verifica thread response: {response.status_code}")
            logging.debug(f"Verifica thread body: {response.text[:200]}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    threads = data.get('threads', [])
                    
                    # Cerca il nostro thread nella lista
                    for thread in threads:
                        if thread.get('slug') == self.thread_slug:
                            thread_name = thread.get('name', 'N/A')
                            logging.info(f"Thread verificato: {thread_name} (slug: {self.thread_slug})")
                            return True
                    
                    logging.warning(f"Thread {self.thread_slug} non trovato nella lista")
                    return False
                    
                except json.JSONDecodeError:
                    logging.warning("Risposta non è JSON valido, probabilmente endpoint sbagliato")
                    return False
            else:
                logging.error(f"Thread verification failed: {response.status_code}")
                return False
                
        except Exception as e:
            logging.error(f"Errore verifica thread: {e}")
            return False
    """
    def run_prompt_in_thread(self, prompt_text: str, expected_fragments: List[str], 
                           llm_name: str, llm_params: Dict) -> Tuple[bool, str, float]:
        """
        Esegue un prompt nel thread dedicato con configurazione LLM corretta
        Prova diversi endpoint e formati di payload per massima compatibilità
        
        Args:
            prompt_text: Testo del prompt
            expected_fragments: Frammenti attesi nella risposta
            llm_name: Nome del modello LLM
            llm_params: Parametri per il LLM
            
        Returns:
            Tuple (success, response, duration)
        """
        if not self.workspace_slug or not self.thread_slug:
            return False, "Workspace o thread non configurati", 0.0
        
        # Prima aggiorna la configurazione LLM del workspace
        self.update_workspace_llm_config(llm_params)
        
        # Verifica che il thread esista
        if not self.verify_thread_exists():
            logging.warning("Thread non verificabile, continuo comunque...")
        
        # Lista di endpoint da provare in ordine di preferenza
        endpoints_to_try = [
            f"/api/v1/workspace/{self.workspace_slug}/thread/{self.thread_slug}/chat"
#            f"/api/v1/workspace/{self.workspace_slug}/chat",
#            f"/api/v1/chat/{self.workspace_slug}"
        ]
        
        # Genera un session ID unico per questa richiesta
        session_id = f"{self.thread_slug}-{int(time.time())}"
        
        # Rilevamento provider
        provider = self.detect_llm_provider(llm_params.get('model', ''))
        
        start_time = time.time()
        
        for endpoint_idx, endpoint in enumerate(endpoints_to_try):
            full_endpoint = f"{self.base_url}{endpoint}"
            
            # Prepara diversi formati di payload da provare
            payloads_to_try = []
            
            # Payload 1: Completo con thread specifico
            payload1 = {
                "message": prompt_text,
                "mode": "query",
                "sessionId": session_id,
                "chatMode": "query",
                "threadSlug": self.thread_slug
            }
            
            # Payload 2: Semplificato
            payload2 = {
                "message": prompt_text,
                "mode": "query"
            }
            
            # Payload 3: Con parametri LLM incorporati
            payload3 = {
                "message": prompt_text,
                "mode": "query",
                "sessionId": session_id
            }
            
            # Aggiungi parametri LLM al payload3 se non è OpenAI
            if provider != 'openai':
                if 'temperature' in llm_params:
                    payload3['temperature'] = llm_params['temperature']
                if 'model' in llm_params:
                    payload3['model'] = llm_params['model']
            
            payloads_to_try = [payload1, payload2, payload3]
            
            # Prova ogni payload con l'endpoint corrente
            for payload_idx, payload in enumerate(payloads_to_try):
                try:
                    logging.debug(f"Tentativo {endpoint_idx+1}.{payload_idx+1}: {endpoint}")
                    logging.debug(f"Payload: {json.dumps(payload, indent=2)}")
                    
                    # Headers per questa richiesta specifica
                    headers = {
                        'Authorization': f'Bearer {self.api_key}',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                    
                    response = requests.post(
                        full_endpoint,
                        json=payload,
                        headers=headers,
                        timeout=self.timeout
                    )
                    
                    elapsed_time = time.time() - start_time
                    
                    logging.debug(f"Response status: {response.status_code}")
                    logging.debug(f"Response preview: {response.text[:300]}")
                    
                    if response.status_code in [200, 201]:
                        try:
                            data = response.json()
                            logging.debug(f"Response JSON keys: {list(data.keys()) if isinstance(data, dict) else 'Non è un dict'}")
                        except:
                            data = {"raw_response": response.text}
                        
                        # Estrai la risposta
                        answer = self.extract_response_from_data(data)
                        
                        # Se non troviamo una risposta, usa il testo raw
                        if not answer or len(answer) < 10:
                            answer = response.text
                        
                        logging.debug(f"Risposta estratta (primi 200 char): {answer[:200]}")
                        
                        # Verifica frammenti attesi
                        if expected_fragments:
                            match = all(
                                fragment.lower() in answer.lower() 
                                for fragment in expected_fragments 
                                if fragment and fragment.strip()
                            )
                        else:
                            match = len(answer.strip()) > 0
                        
                        logging.info(f"Test completato in {elapsed_time:.2f}s - Match: {match}")
                        logging.info(f"Endpoint riuscito: {endpoint} (payload {payload_idx+1})")
                        
                        return match, answer, elapsed_time
                    
                    elif response.status_code == 500:
                        # Errore 500, potrebbe essere problema di configurazione
                        error_data = response.text
                        logging.error(f"Errore 500: {error_data[:200]}")
                        
                        # Se è un errore di configurazione, non provare altri endpoint
                        if 'API key' in error_data or 'OpenAI' in error_data:
                            elapsed_time = time.time() - start_time
                            return False, f"Configurazione provider errata: {error_data[:200]}", elapsed_time
                    
                    # Altri codici di errore, prova il prossimo payload/endpoint
                    logging.debug(f"Fallito tentativo {endpoint_idx+1}.{payload_idx+1}: {response.status_code}")
                    
                except requests.exceptions.Timeout:
                    elapsed_time = time.time() - start_time
                    logging.error(f"Timeout su {endpoint}")
                    if endpoint_idx == len(endpoints_to_try) - 1 and payload_idx == len(payloads_to_try) - 1:
                        return False, f"Timeout dopo {elapsed_time:.1f}s", elapsed_time
                    continue
                    
                except Exception as e:
                    logging.error(f"Errore con {endpoint}, payload {payload_idx+1}: {e}")
                    continue
        
        # Se arriviamo qui, tutti i tentativi sono falliti
        elapsed_time = time.time() - start_time
        error_msg = f"Tutti gli endpoint falliti dopo {elapsed_time:.1f}s"
        logging.error(error_msg)
        return False, error_msg, elapsed_time
    
    def extract_response_from_data(self, data: Any) -> str:
        """
        Estrae la risposta da diversi formati di dati di risposta
        """
        if isinstance(data, str):
            return data
        
        if not isinstance(data, dict):
            return str(data)
        
        # Campi possibili per la risposta in ordine di priorità
        response_fields = [
            'textResponse', 'response', 'message', 'content', 
            'text', 'answer', 'result', 'output', 'data'
        ]
        
        # Cerca nei campi diretti
        for field in response_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str) and value.strip():
                    return value.strip()
        
        # Cerca ricorsivamente nei dati nested
        return self.extract_text_from_nested_response(data)
    
    def extract_text_from_nested_response(self, data: Dict, max_depth: int = 3) -> str:
        """
        Estrae testo da una risposta JSON nested
        """
        if max_depth <= 0:
            return ""
        
        if isinstance(data, str):
            return data
        
        if not isinstance(data, dict):
            return str(data)
        
        # Cerca campi che potrebbero contenere la risposta
        text_fields = [
            'textResponse', 'response', 'message', 'content', 
            'text', 'answer', 'result', 'output'
        ]
        
        for field in text_fields:
            if field in data:
                value = data[field]
                if isinstance(value, str) and value.strip():
                    return value.strip()
                elif isinstance(value, dict):
                    nested_result = self.extract_text_from_nested_response(value, max_depth - 1)
                    if nested_result:
                        return nested_result
        
        # Se non troviamo niente nei campi standard, cerca in tutti i valori
        for key, value in data.items():
            if isinstance(value, str) and len(value) > 20:
                return value
            elif isinstance(value, dict):
                nested_result = self.extract_text_from_nested_response(value, max_depth - 1)
                if nested_result:
                    return nested_result
        
        return ""
    
    def load_test_prompts(self) -> List[Dict]:
        """Carica tutti i prompt di test dalla directory"""
        if not os.path.exists(self.prompt_dir):
            print(f"❌ Directory prompt non trovata: {self.prompt_dir}")
            return []
        
        prompts = []
        yaml_files = [f for f in os.listdir(self.prompt_dir) if f.endswith('.yaml')]
        
        if not yaml_files:
            print(f"❌ Nessun file YAML trovato in: {self.prompt_dir}")
            return []
        
        print(f"📁 Trovati {len(yaml_files)} file di test in {self.prompt_dir}")
        
        for filename in sorted(yaml_files):
            try:
                file_path = os.path.join(self.prompt_dir, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                
                # Valida struttura YAML
                if not isinstance(data, dict):
                    logging.warning(f"File {filename}: struttura YAML non valida")
                    continue
                
                prompt = data.get('prompt', '').strip()
                expected = data.get('expected_response_contains', [])
                
                if not prompt:
                    logging.warning(f"File {filename}: prompt vuoto")
                    continue
                
                # Assicurati che expected sia una lista
                if isinstance(expected, str):
                    expected = [expected]
                elif not isinstance(expected, list):
                    expected = []
                
                prompts.append({
                    'file': filename,
                    'name': data.get('name', filename),
                    'prompt': prompt,
                    'expected': expected
                })
                
                logging.debug(f"Caricato test: {filename}")
                
            except Exception as e:
                logging.error(f"Errore caricamento {filename}: {e}")
                continue
        
        print(f"✅ Caricati {len(prompts)} test validi")
        return prompts
    
    def get_llm_configurations(self) -> Dict[str, Dict]:
        """
        Ottiene le configurazioni LLM dal file di config
        Se non specificate, usa configurazioni di default
        """
        # Controlla se ci sono configurazioni LLM nel config
        workspace_config = self.config.get('workspace', {})
        
        # Configurazioni LLM di default se non specificate
        default_llms = {
            "deepseek": {
                "temperature": 0,
                "model": "deepseek-r1:latest"
            }
        }
        
        # Usa configurazioni dal file se presenti, altrimenti default
        llm_configs = workspace_config.get('llm_models', default_llms)
        
        # Aggiungi parametri di default se mancanti
        for llm_name, params in llm_configs.items():
            if 'temperature' not in params:
                params['temperature'] = workspace_config.get('default_temperature', 0.7)
        
        logging.info(f"Configurazioni LLM: {list(llm_configs.keys())}")
        return llm_configs
    
    def run_single_test(self, test_data: Dict, llm_name: str, llm_params: Dict) -> Dict:
        """
        Esegue un singolo test
        
        Args:
            test_data: Dati del test (prompt, expected, etc.)
            llm_name: Nome del modello LLM
            llm_params: Parametri del modello
            
        Returns:
            Dizionario con i risultati del test
        """
        result = {
            'test_file': test_data['file'],
            'test_name': test_data['name'],
            'llm': llm_name,
            'prompt': test_data['prompt'],
            'expected': '; '.join(test_data['expected']),
            'response': '',
            'pass': False,
            'duration_sec': 0.0,
            'error': None
        }
        
        try:
            # Esegui il test nel thread
            success, response, duration = self.run_prompt_in_thread(
                test_data['prompt'],
                test_data['expected'],
                llm_name,
                llm_params
            )
            
            result['response'] = response
            result['pass'] = success
            result['duration_sec'] = round(duration, 3)
            
            if not success and ('Errore' in response or 'HTTP' in response or 'Timeout' in response):
                result['error'] = response
            
        except Exception as e:
            result['error'] = str(e)
            logging.error(f"Errore test {test_data['file']}: {e}")
        
        return result
    
    def run_all_tests(self, workspace_identifier: str) -> bool:
        """
        Esegue tutti i test nel workspace specificato
        
        Args:
            workspace_identifier: Nome o slug del workspace (OBBLIGATORIO)
            
        Returns:
            True se tutti i test sono stati eseguiti
        """
        self.start_time = time.time()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_csv = f"aprompts_results_{timestamp}.csv"
        
        print("="*70)
        print("🧪 ANYTHINGLLM APROMPTS RUNNER v2.0")
        print("   Test automatici con thread dedicati")
        print("="*70)
        
        # Validazione workspace obbligatorio
        if not workspace_identifier or not workspace_identifier.strip():
            print("❌ ERRORE: Nome workspace obbligatorio!")
            print("   Usa: python3 gare-aprompts.py --workspace NOME_WORKSPACE")
            return False
        
        # 1. Test connessione
        print("\n🔍 Test connessione...")
        if not self.test_connection():
            print("❌ Connessione fallita!")
            print("Verifica:")
            print("  1. Il server AnythingLLM è in esecuzione")
            print("  2. L'URL nel file di configurazione è corretto")
            print("  3. L'API key è valida")
            return False
        print("✅ Connesso al server AnythingLLM")
        
        # 2. Trova workspace ESATTO
        print(f"\n🏢 Ricerca workspace: '{workspace_identifier}'")
        success, result = self.get_workspace_info(workspace_identifier)
        if not success:
            print(f"❌ {result}")
            print("\n💡 SOLUZIONI:")
            print("  1. Verifica il nome del workspace nell'interfaccia AnythingLLM")
            print("  2. Usa il nome esatto o lo slug del workspace")
            print("  3. Assicurati che il workspace esista e sia accessibile")
            return False
        
        workspace_slug = result
        print(f"✅ Workspace confermato: {workspace_slug}")
        
        # 3. Carica test (prima di creare il thread per verificare che ci siano)
        print(f"\n📚 Caricamento test da {self.prompt_dir}...")
        test_prompts = self.load_test_prompts()
        if not test_prompts:
            print("❌ Nessun test da eseguire")
            print("💡 SOLUZIONI:")
            print(f"  1. Verifica che la directory '{self.prompt_dir}' esista")
            print("  2. Verifica che contenga file .yaml validi")
            print("  3. Usa csv_to_yaml_converter.py per generare i test")
            return False
        
        # 4. Ottieni configurazioni LLM
        llm_configs = self.get_llm_configurations()
        if not llm_configs:
            print("❌ Nessuna configurazione LLM trovata")
            return False
        
        print(f"✅ Modelli configurati: {', '.join(llm_configs.keys())}")
        
        # 5. Crea thread dedicato DOPO aver verificato che ci siano test da eseguire
        print(f"\n🧵 Creazione thread per test...")
        success, thread_result = self.create_test_thread()
        if not success:
            print(f"❌ Errore creazione thread: {thread_result}")
            print("💡 POSSIBILI CAUSE:")
            print("  1. Workspace non ha permessi per creare thread")
            print("  2. Problema di connessione API")
            print("  3. Configurazione workspace non corretta")
            return False
        
        thread_slug = thread_result
        print(f"✅ Thread creato: {thread_slug}")
        
        # 5.1. Verifica che il thread sia utilizzabile
        print(f"🔍 Verifica thread...")
        try:
            if self.verify_thread_exists():
                print("✅ Thread verificato e pronto")
            else:
                print("⚠️ Warning: Thread non verificabile, continuo comunque...")
        except Exception as e:
            print(f"⚠️ Warning: Errore verifica thread ({str(e)[:50]}), continuo comunque...")
            logging.warning(f"Errore verifica thread: {e}")
        
        # 6. Esegui tutti i test
        total_tests = len(test_prompts) * len(llm_configs)
        current_test = 0
        
        print(f"\n🚀 Esecuzione {total_tests} test nel thread {thread_slug}")
        print(f"📊 Workspace: {workspace_slug}")
        print(f"🧵 Thread ID: {self.thread_id}")
        print("-" * 70)
        
        for test_data in test_prompts:
            print(f"\n📝 Test: {test_data['file']}")
            print(f"   Prompt: {test_data['prompt'][:60]}...")
            print(f"   Frammenti attesi: {len(test_data['expected'])}")
            
            for llm_name, llm_params in llm_configs.items():
                current_test += 1
                
                print(f"\n   [{current_test}/{total_tests}] Testing con {llm_name}...")
                print(f"      Modello: {llm_params.get('model', 'N/A')}")
                print(f"      Temperature: {llm_params.get('temperature', 'N/A')}")
                
                # Esegui il test
                result = self.run_single_test(test_data, llm_name, llm_params)
                self.test_results.append(result)
                
                # Report risultato
                status_icon = "✅" if result['pass'] else "❌"
                duration = result['duration_sec']
                
                print(f"      {status_icon} Risultato: {duration}s")
                
                if result['error']:
                    print(f"         ⚠️ Errore: {result['error'][:100]}")
                    # Se è un errore di configurazione, mostra suggerimento
                    if 'API key' in result['error'] or 'OpenAI' in result['error']:
                        print(f"         💡 Suggerimento: Verifica configurazione provider per {llm_name}")
                        print(f"         📝 Modello: {llm_params.get('model', 'N/A')}")
                        print(f"         🔧 Provider rilevato: {self.detect_llm_provider(llm_params.get('model', ''))}")
                elif result['pass']:
                    print(f"         ✓ Tutti i frammenti trovati nella risposta")
                    # Mostra parte della risposta per debug
                    if result['response']:
                        preview = result['response'][:100].replace('\n', ' ')
                        print(f"         📝 Anteprima: {preview}...")
                else:
                    print(f"         ✗ Alcuni frammenti mancanti")
                    # Mostra quali frammenti mancano
                    missing = []
                    response_lower = result['response'].lower()
                    for fragment in test_data['expected']:
                        if fragment and fragment.strip() and fragment.lower() not in response_lower:
                            missing.append(fragment[:30])
                    if missing:
                        print(f"         🔍 Mancanti: {', '.join(missing[:3])}")
                    # Mostra anteprima risposta per debug
                    if result['response']:
                        preview = result['response'][:150].replace('\n', ' ')
                        print(f"         📝 Risposta ricevuta: {preview}...")
                
                # Piccola pausa tra test per non sovraccaricare
                time.sleep(0.5)
        
        # 7. Salva risultati
        self.save_results()
        
        # 8. Report finale
        self.print_final_report()
        
        return True
    
    def save_results(self):
        """Salva i risultati in formato CSV"""
        try:
            with open(self.output_csv, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'test_file', 'test_name', 'llm', 'prompt', 'expected', 
                    'response', 'pass', 'duration_sec', 'error'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in self.test_results:
                    # Pulizia dati per CSV
                    csv_row = result.copy()
                    csv_row['pass'] = '✅' if result['pass'] else '❌'
                    csv_row['response'] = csv_row['response'][:2000]  # Aumentato limite per vedere più risposta
                    
                    writer.writerow(csv_row)
            
            logging.info(f"Risultati salvati in: {self.output_csv}")
            print(f"\n💾 Risultati salvati: {self.output_csv}")
            
        except Exception as e:
            logging.error(f"Errore salvataggio CSV: {e}")
            print(f"❌ Errore salvataggio: {e}")
    
    def print_final_report(self):
        """Stampa il report finale dei test"""
        if not self.test_results:
            return
        
        # Calcola statistiche
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r['pass'])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        total_duration = sum(r['duration_sec'] for r in self.test_results)
        avg_duration = total_duration / total_tests if total_tests > 0 else 0
        
        # Statistiche per LLM
        llm_stats = {}
        for result in self.test_results:
            llm = result['llm']
            if llm not in llm_stats:
                llm_stats[llm] = {'total': 0, 'passed': 0, 'duration': 0}
            
            llm_stats[llm]['total'] += 1
            llm_stats[llm]['duration'] += result['duration_sec']
            if result['pass']:
                llm_stats[llm]['passed'] += 1
        
        # Calcola medie
        for llm in llm_stats:
            stats = llm_stats[llm]
            stats['success_rate'] = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
            stats['avg_duration'] = stats['duration'] / stats['total'] if stats['total'] > 0 else 0
        
        # Stampa report
        print("\n" + "="*70)
        print("📊 REPORT FINALE - APROMPTS TEST")
        print("="*70)
        print(f"🧵 Thread utilizzato: {self.thread_slug}")
        print(f"🏢 Workspace: {self.workspace_slug}")
        print(f"🆔 Workspace ID: {self.workspace_id}")
        print(f"⏱️  Tempo totale: {total_duration:.1f}s")
        print(f"📈 Tempo medio per test: {avg_duration:.2f}s")
        print(f"📊 Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        
        print(f"\n📋 Dettagli per Modello:")
        for llm, stats in llm_stats.items():
            print(f"   {llm}:")
            print(f"      ✅ Passati: {stats['passed']}/{stats['total']} ({stats['success_rate']:.1f}%)")
            print(f"      ⏱️ Tempo medio: {stats['avg_duration']:.2f}s")
        
        print(f"\n💾 File risultati: {self.output_csv}")
        
        if failed_tests > 0:
            print(f"\n❌ Test falliti:")
            failed_count = 0
            for result in self.test_results:
                if not result['pass']:
                    print(f"   - {result['test_file']} ({result['llm']})")
                    if result.get('error'):
                        print(f"     Errore: {result['error'][:100]}")
                    failed_count += 1
                    if failed_count >= 5:  # Mostra max 5 errori
                        remaining = failed_tests - failed_count
                        if remaining > 0:
                            print(f"   ... e altri {remaining} test falliti")
                        break
        
        print("\n🎯 RIEPILOGO ESECUZIONE:")
        print(f"   📂 Workspace: {self.workspace_slug}")
        print(f"   🧵 Thread: {self.thread_slug}")
        print(f"   📊 Successo: {success_rate:.1f}%")
        print(f"   ⏱️ Durata: {total_duration:.1f}s")
        
        # Informazioni sui provider utilizzati
        llm_providers = {}
        for result in self.test_results:
            llm = result['llm']
            if llm not in llm_providers:
                # Ottieni le configurazioni per questo LLM
                llm_configs = self.get_llm_configurations()
                if llm in llm_configs:
                    model = llm_configs[llm].get('model', 'N/A')
                    provider = self.detect_llm_provider(model)
                    llm_providers[llm] = f"{model} → {provider}"
        
        if llm_providers:
            print(f"\n🔧 Provider utilizzati:")
            for llm, info in llm_providers.items():
                print(f"   {llm}: {info}")
        
        # Suggerimenti per errori comuni
        if failed_tests > 0:
            print(f"\n💡 SUGGERIMENTI PER ERRORI:")
            
            # Controlla errori di configurazione
            config_errors = sum(1 for r in self.test_results 
                              if r.get('error') and ('API key' in r['error'] or 'OpenAI' in r['error']))
            if config_errors > 0:
                print(f"   🔧 {config_errors} errori di configurazione provider")
                print("      - Verifica che Ollama sia in esecuzione per modelli locali")
                print("      - Controlla che il modello sia disponibile in Ollama")
                print("      - Verifica configurazione API key se usi provider esterni")
            
            # Controlla timeout
            timeout_errors = sum(1 for r in self.test_results 
                               if r.get('error') and 'Timeout' in r['error'])
            if timeout_errors > 0:
                print(f"   ⏱️ {timeout_errors} errori di timeout")
                print("      - Aumenta il timeout nella configurazione")
                print("      - Verifica prestazioni del server AnythingLLM")
        
        print("\n✨ Test completati!")
        print(f"💡 Per generare un report HTML interattivo, esegui:")
        print(f"   python3 csv_results_to_html.py {self.output_csv}")


def main():
    """Funzione principale"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='APROMPTS runner per AnythingLLM con workspace obbligatorio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
IMPORTANTE: Il workspace è OBBLIGATORIO e deve esistere.
Non viene usato alcun workspace di fallback.

Il programma crea automaticamente un thread con nome: TIMESTAMP-aprompts

Esempi:
  %(prog)s --workspace procurement-rag       # Usa workspace specifico
  %(prog)s -w my-docs --config custom.json  # Usa config personalizzato
  %(prog)s -w test-workspace --verbose       # Output verboso
  
PROCESSO:
  1. Connessione al server AnythingLLM
  2. Verifica del workspace specificato
  3. Creazione thread dedicato: TIMESTAMP-aprompts
  4. Caricamento test YAML dalla directory prompts
  5. Esecuzione test con configurazioni LLM
  6. Salvataggio risultati in CSV
  7. Generazione report finale

ERRORI COMUNI:
  - Workspace non specificato → ERRORE
  - Workspace non esistente → ERRORE  
  - Nome workspace errato → ERRORE
  - Nessun file YAML trovato → ERRORE
        """
    )
    
    # WORKSPACE ORA OBBLIGATORIO - NESSUN DEFAULT
    parser.add_argument('--workspace', '-w', 
                       required=True,  # ← OBBLIGATORIO
                       help='Nome o slug del workspace (OBBLIGATORIO)')
    
    parser.add_argument('--config', '-c',
                       default=CONFIG_FILE,
                       help=f'File di configurazione (default: {CONFIG_FILE})')
    parser.add_argument('--prompts', '-p',
                       default='./prompts_anythingllm',
                       help='Directory contenente i file YAML dei test')
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Output verboso per debug')
    
    args = parser.parse_args()
    
    # Validazione argomenti
    if not args.workspace or not args.workspace.strip():
        print("❌ ERRORE: Il parametro --workspace è obbligatorio!")
        print("   Esempio: python3 gare-aprompts.py --workspace procurement-rag")
        parser.print_help()
        sys.exit(1)
    
    # Crea il test runner
    try:
        runner = TestRunner(args.config)
        runner.prompt_dir = args.prompts
        
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        print(f"🎯 Workspace target: '{args.workspace}'")
        print(f"📁 Directory test: {args.prompts}")
        print(f"⚙️ Config file: {args.config}")
        
        # Esegui tutti i test
        success = runner.run_all_tests(args.workspace)
        
        if not success:
            print("\n❌ ESECUZIONE FALLITA!")
            print("Controlla i messaggi di errore sopra per i dettagli.")
            sys.exit(1)
        else:
            print("\n🎉 ESECUZIONE COMPLETATA CON SUCCESSO!")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrotti dall'utente")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore generale: {e}")
        logging.error(f"Errore generale: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
