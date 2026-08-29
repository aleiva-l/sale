"""
Sincroniza la Google Sheet de comercios -> comercios.json

Cómo publicar la Sheet (una vez, sin credenciales ni API keys):
  1. En Google Sheets: Archivo -> Compartir -> Publicar en la web
  2. Elegir la hoja correspondiente y formato "Valores separados por comas (.csv)"
  3. Publicar. Copiar la URL que te da (termina en algo como .../pub?output=csv)
  4. Pegarla abajo en SHEET_CSV_URL (o pasarla por variable de entorno)

Columnas esperadas en la Sheet (deben llamarse así, en la primera fila):
  nombre | rubro | oferta | zona | telefono

Uso:
  python3 sync_sheet_to_json.py
  (genera ./comercios.json en el mismo directorio)
"""

import csv
import io
import json
import os
import sys
import urllib.request

SHEET_CSV_URL = os.environ.get(
    "SHEET_CSV_URL",
    "PEGAR_ACA_LA_URL_DE_PUBLICACION_CSV",
)

CAMPOS_REQUERIDOS = ["nombre", "rubro", "oferta", "zona", "telefono"]
SALIDA = os.environ.get("SALIDA", "comercios.json")


def descargar_csv(url: str) -> str:
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8-sig")  # utf-8-sig: Sheets a veces manda BOM


def csv_a_comercios(texto_csv: str) -> list[dict]:
    lector = csv.DictReader(io.StringIO(texto_csv))

    faltantes = [c for c in CAMPOS_REQUERIDOS if c not in (lector.fieldnames or [])]
    if faltantes:
        raise ValueError(
            f"Faltan columnas en la Sheet: {faltantes}. "
            f"Columnas encontradas: {lector.fieldnames}"
        )

    comercios = []
    for i, fila in enumerate(lector, start=2):  # fila 1 = encabezados
        nombre = (fila.get("nombre") or "").strip()
        if not nombre:
            continue  # fila vacía o incompleta, se ignora

        telefono = (fila.get("telefono") or "").strip()
        telefono = "".join(ch for ch in telefono if ch.isdigit())  # limpia espacios/guiones

        if not telefono:
            print(f"[aviso] fila {i}: '{nombre}' sin teléfono válido, se omite igual el link de WhatsApp quedará roto")

        comercios.append({
            "nombre": nombre,
            "rubro": (fila.get("rubro") or "").strip(),
            "oferta": (fila.get("oferta") or "").strip(),
            "zona": (fila.get("zona") or "").strip(),
            "telefono": telefono,
        })

    return comercios


def main():
    if SHEET_CSV_URL == "PEGAR_ACA_LA_URL_DE_PUBLICACION_CSV":
        print("Falta configurar SHEET_CSV_URL (ver instrucciones arriba del archivo).")
        sys.exit(1)

    print(f"Descargando CSV desde: {SHEET_CSV_URL}")
    texto_csv = descargar_csv(SHEET_CSV_URL)

    comercios = csv_a_comercios(texto_csv)
    if not comercios:
        print("[aviso] no se encontró ningún comercio válido en la Sheet.")

    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(comercios, f, ensure_ascii=False, indent=2)

    print(f"Listo: {len(comercios)} comercios escritos en {SALIDA}")


if __name__ == "__main__":
    main()
