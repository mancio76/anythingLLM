import os
import subprocess
import mimetypes
import shutil

# CONFIGURAZIONE
INPUT_FOLDER = os.getcwd()
OUTPUT_FOLDER = os.path.join(INPUT_FOLDER, "pdf_output")
TEMP_FOLDER = os.path.join(INPUT_FOLDER, "temp_p7m")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

def run_command(cmd):
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Errore comando: {' '.join(cmd)}\n{e}")
        return False

def extract_p7m(p7m_path, out_path):
    cmd = [
        "openssl", "smime",
        "-verify",
        "-in", p7m_path,
        "-inform", "DER",
        "-noverify",
        "-out", out_path
    ]
    return run_command(cmd)

def guess_filetype(filepath):
    mime, _ = mimetypes.guess_type(filepath)
    if mime:
        return mime

    # Fallback: usa comando `file`
    try:
        result = subprocess.run(["file", filepath], capture_output=True, text=True)
        output = result.stdout.lower()
        if "pdf" in output:
            return "application/pdf"
        elif "image" in output:
            return "image"
    except Exception as e:
        print(f"⚠️ Errore durante il file detection: {e}")
    return ""

def apply_ocr(input_file, output_pdf):
    cmd = [
        "ocrmypdf",
        "--image-dpi", "300",
        input_file,
        output_pdf
    ]
    return run_command(cmd)

def convert_p7m_file(p7m_file):
    print(f"📩 Elaboro: {p7m_file}")
    base_name = os.path.splitext(os.path.basename(p7m_file))[0]
    extracted_file = os.path.join(TEMP_FOLDER, base_name)

    # Estrai contenuto dal p7m
    if not extract_p7m(p7m_file, extracted_file):
        print(f"❌ Fallita estrazione da: {p7m_file}")
        return

    filetype = guess_filetype(extracted_file)
    output_pdf = os.path.join(OUTPUT_FOLDER, base_name + ".pdf")

    # Caso 1: è un PDF → lo spostiamo direttamente
    if "pdf" in filetype:
        shutil.move(extracted_file, output_pdf)
        print(f"✅ PDF estratto: {output_pdf}")

    # Caso 2: è immagine → OCR
    elif "image" in filetype:
        if apply_ocr(extracted_file, output_pdf):
            print(f"✅ PDF OCRizzato da immagine: {output_pdf}")
            os.remove(extracted_file)

    # Caso 3: tipo sconosciuto → forziamo OCR su file rinominato .pdf
    else:
        print(f"⚠️ Tipo file non riconosciuto: {filetype}, provo OCR forzato...")
        forced_path = extracted_file + ".pdf"
        os.rename(extracted_file, forced_path)
        if apply_ocr(forced_path, output_pdf):
            print(f"✅ PDF OCRizzato forzando tipo: {output_pdf}")
            os.remove(forced_path)
        else:
            print(f"❌ Impossibile convertire {p7m_file}")

def main():
    p7m_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".p7m")]
    if not p7m_files:
        print("⚠️ Nessun file .p7m trovato nella cartella.")
        return

    for file in p7m_files:
        full_path = os.path.join(INPUT_FOLDER, file)
        convert_p7m_file(full_path)

if __name__ == "__main__":
    main()
