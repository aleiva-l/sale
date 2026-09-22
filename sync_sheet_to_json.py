import csv
import io
import json
import os
import sys
import unicodedata
import urllib.request


SHEET_ID = os.environ.get("1WByz_vxmvynFqIo2IwmvNgD1HsR6DJ3kDshh-Qb3o-c")
SHEET_GID = os.environ.get("1728155305", "0")

OUTPUT_FILE = "comercios.json"


if not SHEET_ID:
    print("ERROR: falta la variable SHEET_ID")
    sys.exit(1)


def normalizar(texto):
    if texto is None:
        return ""

    texto = str(texto).strip().lower()

    # sacar acentos
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )

    return " ".join(texto.split())


ALIASES = {
    "nombre": [
        "nombre",
        "comercio",
        "nombre comercio",
        "nombre del comercio",
    ],
    "rubro": [
        "rubro",
        "categoria",
    ],
    "oferta": [
        "oferta",
        "descuento",
        "promocion",
    ],
    "zona": [
        "zona",
        "ubicacion",
        "direccion",
    ],
    "telefono": [
        "telefono",
        "whatsapp",
        "celular",
    ],
    "imagen": [
        "imagen",
        "foto",
        "url imagen",
        "url de imagen",
    ],
}


def obtener_valor(fila, campo):
    for alias in ALIASES[campo]:
        alias_normalizado = normalizar(alias)

        if alias_normalizado in fila:
            return fila[alias_normalizado].strip()

    return ""


url = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    f"/export?format=csv&gid={SHEET_GID}"
)

print(f"Descargando Google Sheet gid={SHEET_GID}...")


request = urllib.request.Request(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        contenido = response.read().decode("utf-8-sig")

except Exception as e:
    print(f"ERROR descargando Google Sheet: {e}")
    sys.exit(1)


# Si Google devuelve una página de login en vez del CSV
if "<html" in contenido.lower():
    print(
        "ERROR: Google devolvió HTML en lugar de CSV. "
        "Verificá que la Sheet tenga acceso público de lectura."
    )
    sys.exit(1)


reader = csv.DictReader(io.StringIO(contenido))


if not reader.fieldnames:
    print("ERROR: la Sheet no tiene encabezados")
    sys.exit(1)


comercios = []


for raw_row in reader:

    fila = {
        normalizar(k): str(v or "").strip()
        for k, v in raw_row.items()
        if k
    }

    comercio = {
        "nombre": obtener_valor(fila, "nombre"),
        "rubro": obtener_valor(fila, "rubro"),
        "oferta": obtener_valor(fila, "oferta"),
        "zona": obtener_valor(fila, "zona"),
        "telefono": obtener_valor(fila, "telefono"),
        "imagen": obtener_valor(fila, "imagen"),
    }

    # ignoramos filas vacías
    if not comercio["nombre"]:
        continue

    comercios.append(comercio)


with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(
        comercios,
        f,
        ensure_ascii=False,
        indent=2,
    )
    f.write("\n")


print(f"OK: {len(comercios)} comercios escritos en {OUTPUT_FILE}")
