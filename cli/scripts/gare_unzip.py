
# -*- coding: utf-8 -*-
"""
Modulo 2: Unzip gestito separatamente.
"""
from pathlib import Path
import zipfile
import os

def extract_zip(zip_path: Path, dest_dir: Path, verbose: bool = False) -> list[Path]:
    """
    Estrae uno ZIP in dest_dir e ritorna la lista dei file estratti (solo file, no directory).
    """
    files: list[Path] = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        # Protezione base contro ZipSlip
        for member in zf.infolist():
            extracted_path = Path(dest_dir, member.filename).resolve()
            if not str(extracted_path).startswith(str(dest_dir.resolve())):
                raise RuntimeError(f"Percorso sospetto nello ZIP: {member.filename}")
        zf.extractall(dest_dir)

    # Raccogli file
    for root, _, filenames in os.walk(dest_dir):
        for fn in filenames:
            p = Path(root) / fn
            if p.is_file():
                files.append(p)
                if verbose:
                    print(f"   ↳ {p.relative_to(dest_dir)}")
    return files
