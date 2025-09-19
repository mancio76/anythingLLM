# AnythingLLM Utilities Toolkit

Collezione di script Python per analisi automatizzata documentale e upload verso AnythingLLM.

⚠️ Le API key sono state oscurate automaticamente.

## 🗂 Struttura

- `scripts/`: contiene tutti gli script Python e shell.
- `config/`: contiene la configurazione AnythingLLM con chiavi rimosse.
- `requirements.txt`: tutte le librerie necessarie.
- `deploy_to_github.sh`: script per push automatico su GitHub.

## 🛠 Uso

```bash
git clone https://github.com/TUO-USERNAME/anythingllm-utils.git
cd anythingllm-utils
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Come eseguire gli Steps di anything uploader

Preparare i files

1. caricare lo zip contenente la gara

python3 gare_zip_uploader\_fixed.py prj\_39450.zip --verbose

1. generare le domande 

python3 csv_to_yaml\_converter.001.py Checklist\\ default\\ prj_39450.xlsx

1. eseguire le domande

python3 aprompts\_system.py --workspace prj_39450 --verbose

1. e se voglio eseguire le domande con un altro modello?

e' possibile definire delle copie del file di configurazioen standard e riferire a questo durante l'esecuzione di aprompt

python3 aprompts\_system.py --workspace prj_39450 --config agare-mistral.json --verbose

20250829 Impostata una nuova versione di aprompt che consente di utilizzare llm di sistema senza dover modificare la configurazione del singolo thread

--use-system-llm 

  
Implementato anche la modalita' chat o query es. parametro (se non specificato il default e' chat)

\--chat-mode query --use-system-llm --user-id 2 --verbose

definito anche lo user di esecuzione delle query (by default e' 1) es.

--user-id 2 


## 🚀 Deploy su GitHub

```bash
chmod +x deploy_to_github.sh
./deploy_to_github.sh
```
