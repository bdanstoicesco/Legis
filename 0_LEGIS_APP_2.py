import os
import json
import re
import requests
import urllib3
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# --- INITIALIZARE ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BASE_PATH = "/Volumes/DATA_EXT/Legis"
EU_PATH = os.path.join(BASE_PATH, "EU")
DATASET_FILE = os.path.join(BASE_PATH, "dataset_ai.jsonl")
OLLAMA_MODEL = "llama3.1:8b" 
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}

def show_files():
    """Afișează ce avem în bibliotecă."""
    print("\n📚 BIBLIOTECA LOCALĂ:")
    found = False
    for folder in [BASE_PATH, EU_PATH]:
        if not os.path.exists(folder): continue
        files = [f for f in os.listdir(folder) if f.endswith(".txt") and not f.startswith(".")]
        if files:
            print(f"  [{os.path.basename(folder)}]:")
            for f in files:
                print(f"    - {f}")
            found = True
    if not found: print("  (GOL - Descarcă acte folosind opțiunea 1)")

def clean_filenames():
    """Redenumește fișierele haotice în nume curate."""
    print("\n🧹 Curățare nume fișiere pe Volume...")
    for folder in [BASE_PATH, EU_PATH]:
        if not os.path.exists(folder): continue
        for file in os.listdir(folder):
            if file.endswith(".txt") and not file.startswith("."):
                # Curățare: scoatem cifre de start, date lungi, spații multiple
                name = re.sub(r'^\d+\.\s*', '', file)
                name = re.sub(r'\s*\d{8,}.*', '', name)
                name = name.replace(" ", "_").replace("__", "_").strip("_")
                if not name.endswith(".txt"): name += ".txt"
                
                old_p, new_p = os.path.join(folder, file), os.path.join(folder, name)
                if old_p != new_p:
                    os.rename(old_p, new_p)
    print("✨ Nume curățate.")

def rebuild_dataset():
    clean_filenames()
    print("\n📦 Sincronizare creier AI (RAG Engine)...")
    count = 0
    with open(DATASET_FILE, 'w', encoding='utf-8') as f_out:
        for folder in [BASE_PATH, EU_PATH]:
            if not os.path.exists(folder): continue
            for file in os.listdir(folder):
                if file.endswith(".txt"):
                    count += 1
                    with open(os.path.join(folder, file), 'r', encoding='utf-8') as f_in:
                        text = f_in.read()
                        # Segmente mici (1500 chars) pentru a nu amesteca legile
                        chunks = [text[i:i+1500] for i in range(0, len(text), 1200)]
                        for chunk in chunks:
                            f_out.write(json.dumps({"doc": file, "text": chunk.strip()}, ensure_ascii=False) + '\n')
    print(f"✨ Gata! {count} acte pregătite.")

def ask_ai(query):
    query_clean = re.sub(r'[^\w\s]', ' ', query).lower()
    keywords = [w for w in query_clean.split() if len(w) > 2]
    
    context_matches = []
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # PAS 1: Căutare EXCLUSIVĂ în fișierul care seamănă cu întrebarea (Filtrare Hard)
            target_keywords = [k for k in keywords if k not in ['cod', 'art', 'lege']]
            for line in lines:
                data = json.loads(line)
                doc_name = data['doc'].lower()
                # Dacă întrebarea conține "fiscal" și fișierul conține "fiscal", prioritizăm
                if any(tk in doc_name for tk in target_keywords):
                    if any(kw in data['text'].lower() for kw in keywords):
                        context_matches.append(f"[SURSA: {data['doc']}]\n{data['text']}")
                if len(context_matches) >= 6: break
            
            # PAS 2: Dacă nu am găsit nimic specific, căutăm general
            if not context_matches:
                for line in lines:
                    data = json.loads(line)
                    if all(kw in data['text'].lower() for kw in keywords[:2]):
                        context_matches.append(f"[SURSA: {data['doc']}]\n{data['text']}")
                    if len(context_matches) >= 5: break

    context_str = "\n\n".join(context_matches) if context_matches else "FĂRĂ CONTEXT."
    prompt = f"Ești expert juridic. Răspunde strict pe baza contextului: {context_str}\n\nÎntrebare: {query}"

    try:
        print(f"🤖 Interogare Ollama (Context: {len(context_matches)} fragmente)...")
        res = requests.post("http://localhost:11434/api/generate", 
                            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False, 
                                  "options": {"temperature": 0.0, "num_ctx": 10000}}, timeout=120)
        print(f"\n🤖 RĂSPUNS AI:\n{'-'*30}\n{res.json().get('response')}\n{'-'*30}")
    except: print("❌ Eroare: Ollama nu răspunde.")

def get_act_content(termen):
    # (Funcția de download rămâne neschimbată)
    print(f"🔍 Căutare: {termen}...")
    try:
        url_ro = f"https://legislatie.just.ro/Public/RezultateCautare?titlu={termen.replace(' ', '+')}"
        res = requests.get(url_ro, headers=HEADERS, verify=False, timeout=10)
        soup = BeautifulSoup(res.text, 'lxml')
        a_tag = next((a for a in soup.find_all('a', href=True) if "DetaliiDocument" in a['href']), None)
        if not a_tag: return print("❌ Act negăsit.")
        doc_id = re.search(r'DetaliiDocument/(\d+)', a_tag['href']).group(1)
        res_text = requests.get(f"https://legislatie.just.ro/Public/DetaliiDocumentAfis/{doc_id}", headers=HEADERS, verify=False)
        s_text = BeautifulSoup(res_text.text, 'lxml')
        content = s_text.find('div', {'id': 'divTextAct'}) or s_text.find('body')
        for s in content(["script", "style", "nav"]): s.decompose()
        with open(os.path.join(BASE_PATH, f"{termen}.txt"), "w", encoding="utf-8") as f:
            f.write(content.get_text(separator='\n', strip=True))
        print("✅ Descărcat.")
    except Exception as e: print(f"❌ Eroare: {e}")

def main():
    while True:
        show_files()
        print("\n1. Adaugă Act | 2. Sincronizează (Update AI) | 3. Întreabă AI | 4. Ieșire")
        cmd = input("Alege: ")
        if cmd == "1": get_act_content(input("Nume act: "))
        elif cmd == "2": rebuild_dataset()
        elif cmd == "3": ask_ai(input("Întrebare: "))
        elif cmd == "4": break

if __name__ == "__main__":
    main()
