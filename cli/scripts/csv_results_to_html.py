#!/usr/bin/env python3
"""
Converte il CSV dei risultati test in un report HTML interattivo
"""

import csv
import os
from datetime import datetime
from typing import List, Dict, Any
import html

def generate_html_report(csv_file: str, output_file: str = "test_report.html"):
    """
    Genera un report HTML dai risultati CSV
    
    Args:
        csv_file: Path del file CSV con i risultati
        output_file: Nome del file HTML da generare
    """
    
    # Leggi i dati dal CSV
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            results = list(reader)
    except FileNotFoundError:
        print(f"❌ File {csv_file} non trovato!")
        return False
    except Exception as e:
        print(f"❌ Errore lettura CSV: {e}")
        return False
    
    if not results:
        print("⚠️ Nessun risultato trovato nel CSV")
        return False
    
    # Calcola statistiche
    stats = calculate_statistics(results)
    
    # Genera HTML
    html_content = generate_html(results, stats)
    
    # Salva il file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"✅ Report HTML generato: {output_file}")
        return True
    except Exception as e:
        print(f"❌ Errore scrittura HTML: {e}")
        return False


def calculate_statistics(results: List[Dict]) -> Dict[str, Any]:
    """Calcola le statistiche dai risultati"""
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.get('pass') in ['✅', 'True', 'true', '1'])
    failed_tests = total_tests - passed_tests
    
    # Statistiche per LLM
    llm_stats = {}
    for result in results:
        llm = result.get('llm', 'Unknown')
        if llm not in llm_stats:
            llm_stats[llm] = {'total': 0, 'passed': 0, 'failed': 0, 'durations': []}
        
        llm_stats[llm]['total'] += 1
        
        if result.get('pass') in ['✅', 'True', 'true', '1']:
            llm_stats[llm]['passed'] += 1
        else:
            llm_stats[llm]['failed'] += 1
        
        try:
            duration = float(result.get('duration_sec', 0))
            llm_stats[llm]['durations'].append(duration)
        except:
            pass
    
    # Calcola medie durata
    for llm in llm_stats:
        durations = llm_stats[llm]['durations']
        if durations:
            llm_stats[llm]['avg_duration'] = sum(durations) / len(durations)
            llm_stats[llm]['min_duration'] = min(durations)
            llm_stats[llm]['max_duration'] = max(durations)
        else:
            llm_stats[llm]['avg_duration'] = 0
            llm_stats[llm]['min_duration'] = 0
            llm_stats[llm]['max_duration'] = 0
    
    return {
        'total': total_tests,
        'passed': passed_tests,
        'failed': failed_tests,
        'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
        'llm_stats': llm_stats,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def generate_html(results: List[Dict], stats: Dict) -> str:
    """Genera il contenuto HTML completo"""
    
    # Prepara i risultati per il template
    test_results = []
    for idx, result in enumerate(results, 1):
        # Determina lo stato del test
        is_passed = result.get('pass') in ['✅', 'True', 'true', '1']
        status_icon = '✅' if is_passed else '❌'
        status_class = 'passed' if is_passed else 'failed'
        
        # Tronca risposte lunghe per la visualizzazione iniziale
        response_preview = result.get('response', '')[:200]
        response_full = html.escape(result.get('response', ''))
        
        test_results.append({
            'idx': idx,
            'test_file': result.get('test_file', 'N/A'),
            'llm': result.get('llm', 'N/A'),
            'prompt': html.escape(result.get('prompt', 'N/A')),
            'expected': html.escape(result.get('expected', 'N/A')),
            'response_preview': html.escape(response_preview),
            'response_full': response_full,
            'status_icon': status_icon,
            'status_class': status_class,
            'duration': result.get('duration_sec', 'N/A')
        })
    
    # Template HTML con CSS (parentesi graffe raddoppiate per .format())
    html_template = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Test AnythingLLM</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header .timestamp {{
            opacity: 0.9;
            font-size: 0.9em;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}
        
        .stat-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
            margin: 10px 0;
        }}
        
        .stat-card .label {{
            color: #6c757d;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .stat-card.success .value {{
            color: #28a745;
        }}
        
        .stat-card.danger .value {{
            color: #dc3545;
        }}
        
        .filters {{
            padding: 20px 30px;
            background: #fff;
            border-bottom: 1px solid #dee2e6;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .filter-group {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .filter-group label {{
            font-weight: 500;
            color: #495057;
        }}
        
        select, input[type="text"] {{
            padding: 8px 12px;
            border: 1px solid #ced4da;
            border-radius: 5px;
            font-size: 14px;
        }}
        
        input[type="text"] {{
            width: 300px;
        }}
        
        .results {{
            padding: 30px;
        }}
        
        .test-card {{
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 10px;
            margin-bottom: 20px;
            overflow: hidden;
            transition: all 0.3s ease;
        }}
        
        .test-card:hover {{
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
        }}
        
        .test-card.passed {{
            border-left: 4px solid #28a745;
        }}
        
        .test-card.failed {{
            border-left: 4px solid #dc3545;
        }}
        
        .test-header {{
            padding: 15px 20px;
            background: #f8f9fa;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }}
        
        .test-header:hover {{
            background: #e9ecef;
        }}
        
        .test-info {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        
        .test-number {{
            font-size: 1.2em;
            font-weight: bold;
            color: #6c757d;
        }}
        
        .test-file {{
            color: #495057;
            font-weight: 500;
        }}
        
        .badge {{
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        
        .badge.llm {{
            background: #e7f3ff;
            color: #0066cc;
        }}
        
        .badge.duration {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .test-body {{
            padding: 20px;
            display: none;
        }}
        
        .test-body.expanded {{
            display: block;
        }}
        
        .section {{
            margin-bottom: 20px;
        }}
        
        .section-title {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 1px;
        }}
        
        .section-content {{
            background: #f8f9fa;
            padding: 12px;
            border-radius: 5px;
            color: #212529;
            line-height: 1.6;
        }}
        
        .response-content {{
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        
        .expected-items {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }}
        
        .expected-item {{
            background: #e9ecef;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        
        .llm-summary {{
            margin-top: 40px;
            padding: 30px;
            background: #f8f9fa;
        }}
        
        .llm-summary h2 {{
            margin-bottom: 20px;
            color: #495057;
        }}
        
        .llm-table {{
            width: 100%;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }}
        
        .llm-table th {{
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 500;
        }}
        
        .llm-table td {{
            padding: 15px;
            border-bottom: 1px solid #dee2e6;
        }}
        
        .llm-table tr:last-child td {{
            border-bottom: none;
        }}
        
        .llm-table tr:hover {{
            background: #f8f9fa;
        }}
        
        .progress-bar {{
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            border-radius: 10px;
            transition: width 0.3s ease;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            
            .filters {{
                flex-direction: column;
                align-items: stretch;
            }}
            
            .filter-group {{
                flex-direction: column;
                align-items: stretch;
            }}
            
            input[type="text"] {{
                width: 100%;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Report Test AnythingLLM</h1>
            <div class="timestamp">Generato il: {timestamp}</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Test Totali</div>
                <div class="value">{total_tests}</div>
            </div>
            <div class="stat-card success">
                <div class="label">Passati</div>
                <div class="value">{passed_tests}</div>
            </div>
            <div class="stat-card danger">
                <div class="label">Falliti</div>
                <div class="value">{failed_tests}</div>
            </div>
            <div class="stat-card">
                <div class="label">Success Rate</div>
                <div class="value">{success_rate:.1f}%</div>
            </div>
        </div>
        
        <div class="filters">
            <div class="filter-group">
                <label>Filtra per stato:</label>
                <select id="statusFilter" onchange="filterResults()">
                    <option value="all">Tutti</option>
                    <option value="passed">✅ Passati</option>
                    <option value="failed">❌ Falliti</option>
                </select>
            </div>
            
            <div class="filter-group">
                <label>Filtra per LLM:</label>
                <select id="llmFilter" onchange="filterResults()">
                    <option value="all">Tutti</option>
                    {llm_options}
                </select>
            </div>
            
            <div class="filter-group">
                <label>Cerca:</label>
                <input type="text" id="searchInput" placeholder="Cerca nei prompt o risposte..." onkeyup="filterResults()">
            </div>
        </div>
        
        <div class="results" id="results">
            {test_cards}
        </div>
        
        <div class="llm-summary">
            <h2>📈 Riepilogo per Modello LLM</h2>
            <table class="llm-table">
                <thead>
                    <tr>
                        <th>Modello</th>
                        <th>Test Totali</th>
                        <th>Passati</th>
                        <th>Falliti</th>
                        <th>Success Rate</th>
                        <th>Tempo Medio (s)</th>
                    </tr>
                </thead>
                <tbody>
                    {llm_rows}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        // Espandi/comprimi dettagli test
        function toggleTest(idx) {{
            const body = document.getElementById('test-body-' + idx);
            body.classList.toggle('expanded');
        }}
        
        // Filtra risultati
        function filterResults() {{
            const statusFilter = document.getElementById('statusFilter').value;
            const llmFilter = document.getElementById('llmFilter').value;
            const searchInput = document.getElementById('searchInput').value.toLowerCase();
            
            const testCards = document.querySelectorAll('.test-card');
            
            testCards.forEach(card => {{
                let show = true;
                
                // Filtra per stato
                if (statusFilter !== 'all') {{
                    show = show && card.classList.contains(statusFilter);
                }}
                
                // Filtra per LLM
                if (llmFilter !== 'all') {{
                    const llmBadge = card.querySelector('.badge.llm');
                    show = show && llmBadge && llmBadge.textContent === llmFilter;
                }}
                
                // Filtra per ricerca
                if (searchInput) {{
                    const text = card.textContent.toLowerCase();
                    show = show && text.includes(searchInput);
                }}
                
                card.style.display = show ? 'block' : 'none';
            }});
        }}
        
        // Espandi tutti
        function expandAll() {{
            document.querySelectorAll('.test-body').forEach(body => {{
                body.classList.add('expanded');
            }});
        }}
        
        // Comprimi tutti
        function collapseAll() {{
            document.querySelectorAll('.test-body').forEach(body => {{
                body.classList.remove('expanded');
            }});
        }}
    </script>
</body>
</html>"""
    
    # Genera opzioni LLM per il filtro
    llm_options = '\n'.join([
        f'<option value="{llm}">{llm}</option>'
        for llm in stats['llm_stats'].keys()
    ])
    
    # Genera card dei test
    test_cards = []
    for test in test_results:
        expected_items = test['expected'].split(';') if ';' in test['expected'] else [test['expected']]
        expected_html = '\n'.join([
            f'<span class="expected-item">{item.strip()}</span>'
            for item in expected_items if item.strip()
        ])
        
        card_html = f"""
        <div class="test-card {test['status_class']}" data-idx="{test['idx']}">
            <div class="test-header" onclick="toggleTest({test['idx']})">
                <div class="test-info">
                    <span class="test-number">#{test['idx']}</span>
                    <span class="test-file">{test['test_file']}</span>
                    <span class="badge llm">{test['llm']}</span>
                    <span class="badge duration">⏱️ {test['duration']}s</span>
                </div>
                <div class="test-status">
                    <span style="font-size: 1.5em;">{test['status_icon']}</span>
                </div>
            </div>
            <div class="test-body" id="test-body-{test['idx']}">
                <div class="section">
                    <div class="section-title">Prompt</div>
                    <div class="section-content">{test['prompt']}</div>
                </div>
                
                <div class="section">
                    <div class="section-title">Frammenti Attesi</div>
                    <div class="section-content">
                        <div class="expected-items">
                            {expected_html}
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-title">Risposta</div>
                    <div class="section-content">
                        <div class="response-content">{test['response_full']}</div>
                    </div>
                </div>
            </div>
        </div>"""
        test_cards.append(card_html)
    
    # Genera righe tabella LLM
    llm_rows = []
    for llm, llm_stat in stats['llm_stats'].items():
        success_rate = (llm_stat['passed'] / llm_stat['total'] * 100) if llm_stat['total'] > 0 else 0
        
        row_html = f"""
        <tr>
            <td><strong>{llm}</strong></td>
            <td>{llm_stat['total']}</td>
            <td style="color: #28a745;">{llm_stat['passed']}</td>
            <td style="color: #dc3545;">{llm_stat['failed']}</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {success_rate}%;"></div>
                </div>
                <span>{success_rate:.1f}%</span>
            </td>
            <td>{llm_stat['avg_duration']:.2f}</td>
        </tr>"""
        llm_rows.append(row_html)
    
    # Sostituisci i placeholder nel template
    html_content = html_template.format(
        timestamp=stats['timestamp'],
        total_tests=stats['total'],
        passed_tests=stats['passed'],
        failed_tests=stats['failed'],
        success_rate=stats['success_rate'],
        llm_options=llm_options,
        test_cards='\n'.join(test_cards),
        llm_rows='\n'.join(llm_rows)
    )
    
    return html_content


def main():
    """Funzione principale"""
    import sys
    
    print("="*60)
    print("🔄 CONVERTITORE CSV → HTML REPORT")
    print("="*60)
    
    # Determina il file CSV da usare
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = "test_results.csv"
        print(f"ℹ️  Uso file di default: {csv_file}")
        print("   Per specificare un altro file: python3 script.py percorso/file.csv")
    
    # Determina il file HTML di output
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        output_file = "test_report.html"
    
    if not os.path.exists(csv_file):
        print(f"\n❌ File {csv_file} non trovato!")
        print("   Assicurati di aver eseguito prima i test con gare-test-new.py")
        return
    
    print(f"\n📂 Input: {csv_file}")
    print(f"📄 Output: {output_file}")
    
    # Genera il report
    if generate_html_report(csv_file, output_file):
        print("\n✨ Report generato con successo!")
        print(f"   Apri {output_file} nel browser per visualizzarlo")
        
        # Prova ad aprire automaticamente nel browser
        try:
            import webbrowser
            webbrowser.open(f"file://{os.path.abspath(output_file)}")
            print("   ✅ Apertura automatica nel browser...")
        except:
            pass


if __name__ == "__main__":
    main()