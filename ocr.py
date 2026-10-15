"""
OCR offline con Tesseract + extraccion de datos con expresiones regulares.

Se ejecuta UNA VEZ, antes de levantar el webhook:
    python ocr.py

Lee las imagenes de documentos/, extrae el texto con Tesseract, busca campos
con regex (fechas, importes, referencias) y lo guarda todo en
datos/documentos.json. El webhook solo lee ese JSON: el OCR nunca va dentro de
la peticion porque Dialogflow corta a los 5 segundos.
"""

import json
import re
import shutil
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

# Configuracion

if shutil.which("tesseract") is None:
    ejecutable_windows = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if ejecutable_windows.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(ejecutable_windows)

RAIZ = Path(__file__).parent
CARPETA = RAIZ / "documentos"
SALIDA = RAIZ / "datos" / "documentos.json"
EXTENSIONES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")

# --psm 6 = "un bloque de texto uniforme". Vale para nuestros documentos: una
# sola columna de texto, con tablas hechas de lineas alineadas.
CONFIG_TESSERACT = "--psm 6"


# Extraccion de texto

def leer_documento(ruta: Path) -> str:
    """Pasa una imagen por Tesseract y devuelve el texto reconocido."""
    imagen = Image.open(ruta)

    # Preprocesado: escala de grises + autocontraste. Se compararon 6 variantes
    # contra el texto original: el autocontraste dejo la menor tasa de errores
    # (en numeros, 0 frente a 3 con solo gris). Binarizar sin mas empeoraba
    # (10 numeros perdidos) y ampliar la imagen no aportaba nada.
    imagen = ImageOps.autocontrast(imagen.convert("L"), cutoff=2)

    return pytesseract.image_to_string(
        imagen,
        lang="spa",              # sin esto Tesseract asume ingles y rompe los acentos
        config=CONFIG_TESSERACT,
    )


# Extraccion de campos con regex (requisito del enunciado)

PATRONES = {
    # Fechas tipo 15/09/2026
    "fecha": r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    # Importes tipo 18,00 EUR, 1.250,00 EUR o 5 euros
    "importe": r"\b\d{1,3}(?:\.\d{3})*(?:,\d{2})?\s?(?:€|EUR|euros?)\b",
    # Referencias tipo REF-SNES-001 o REF-GAR-2026
    "referencia": r"\bREF-[A-Z0-9]{2,5}-\d{3,4}\b",
}


def extraer_campos(texto: str) -> dict[str, list[str]]:
    """Busca los PATRONES dentro de un texto ya reconocido (sin repetidos)."""
    campos = {}
    for nombre, patron in PATRONES.items():
        encontrados = re.findall(patron, texto)
        campos[nombre] = list(dict.fromkeys(encontrados))
    return campos


# Programa principal

def main():
    if not CARPETA.exists():
        print(f"No existe la carpeta {CARPETA}. Ejecuta antes generar_documentos.py")
        return

    documentos = {}
    for ruta in sorted(CARPETA.iterdir()):
        if ruta.suffix.lower() not in EXTENSIONES:
            continue
        texto = leer_documento(ruta).strip()
        campos = extraer_campos(texto)
        documentos[ruta.name] = {"texto": texto, "campos": campos}
        print(f"OCR OK: {ruta.name} ({len(texto)} caracteres)")
        for nombre, valores in campos.items():
            print(f"    {nombre}: {valores}")

    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(documentos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado en {SALIDA} ({len(documentos)} documentos)")


if __name__ == "__main__":
    main()
