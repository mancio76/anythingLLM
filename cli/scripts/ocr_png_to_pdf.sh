#!/bin/bash

# Verifica dipendenze
if ! command -v ocrmypdf &> /dev/null; then
    echo "⚠️  Errore: ocrmypdf non trovato. Installa con: pip install ocrmypdf"
    exit 1
fi

if ! command -v convert &> /dev/null; then
    echo "⚠️  Errore: ImageMagick (convert) non trovato. Installa con: sudo apt install imagemagick"
    exit 1
fi

# Estensioni supportate
extensions=("*.png" "*.jpg" "*.jpeg")

# Costruzione lista file
files=()
if [ "$#" -eq 0 ]; then
    echo "🔍 Nessun file specificato. Scansiono *.png, *.jpg, *.jpeg nella directory corrente..."
    for ext in "${extensions[@]}"; do
        for f in $ext; do
            [ -e "$f" ] && files+=("$f")
        done
    done
else
    files=("$@")
fi

# Elaborazione
for img in "${files[@]}"; do
    if [[ "$img" =~ \.(png|jpg|jpeg)$ ]]; then
        base="${img%.*}"
        temp_img="${base}_flat.png"
        output="${base}_ocr.pdf"

        echo "🖼  Preprocessing: rimozione canale alfa e normalizzazione di $img → $temp_img"
        convert "$img" -background white -alpha remove -alpha off "$temp_img"

        echo "📄 OCR: $temp_img → $output"
        ocrmypdf "$temp_img" "$output" --image-dpi 300 --output-type pdf

        if [ $? -eq 0 ]; then
            echo "✅ OK: $output creato"
            rm "$temp_img"
        else
            echo "❌ Errore su: $img"
        fi
    else
        echo "⏭ Ignoro file non supportato: $img"
    fi
done
