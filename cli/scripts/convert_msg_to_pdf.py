import os
import re
import sys
import extract_msg
import pdfkit

# Configurazione
INPUT_FOLDER = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
OUTPUT_FOLDER = os.path.join(INPUT_FOLDER, "pdf_output")
SAVE_ATTACHMENTS = True

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def sanitize_filename(name):
    return re.sub(r'[^\w\-_.]', '_', name)

def convert_msg_to_pdf(filepath):
    print(f"📩 Elaboro: {filepath}")
    msg = extract_msg.Message(filepath)
    msg_sender = msg.sender or ""
    msg_to = msg.to or ""
    msg_date = msg.date or ""
    msg_subject = msg.subject or "email_senza_oggetto"
    msg_body = msg.body or ""

    safe_subject = sanitize_filename(msg_subject)
    base_filename = os.path.splitext(os.path.basename(filepath))[0]
    html_filename = os.path.join(OUTPUT_FOLDER, f"{base_filename}.html")
    pdf_filename = os.path.join(OUTPUT_FOLDER, f"{base_filename}.pdf")

    html = f"""
    <html>
    <body>
    <h2>{msg_subject}</h2>
    <p><strong>Da:</strong> {msg_sender}<br>
    <strong>A:</strong> {msg_to}<br>
    <strong>Data:</strong> {msg_date}</p>
    <hr>
    <pre>{msg_body}</pre>
    </body>
    </html>
    """

    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html)

    pdfkit.from_file(html_filename, pdf_filename)
    print(f"✅ PDF salvato: {pdf_filename}")

    if SAVE_ATTACHMENTS and msg.attachments:
        att_dir = os.path.join(OUTPUT_FOLDER, f"{base_filename}_attachments")
        os.makedirs(att_dir, exist_ok=True)
        for att in msg.attachments:
            att_name = att.longFilename or att.shortFilename or "allegato.bin"
            att_path = os.path.join(att_dir, sanitize_filename(att_name))
            att.save(customPath=att_path)
            print(f"📎 Allegato salvato: {att_path}")

    os.remove(html_filename)

def main():
    msg_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".msg")]
    if not msg_files:
        print("⚠️  Nessun file .msg trovato in", INPUT_FOLDER)
        return

    for file in msg_files:
        try:
            full_path = os.path.join(INPUT_FOLDER, file)
            convert_msg_to_pdf(full_path)
        except Exception as e:
            print(f"❌ Errore su {file}: {e}")

if __name__ == "__main__":
    main()
