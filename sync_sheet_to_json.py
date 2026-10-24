import csv
import io
import json
import os
import sys
import unicodedata
import urllib.request
from urllib.parse import urlparse

SHEET_ID = os.environ.get("SHEET_ID")
SHEET_GID = os.environ.get("SHEET_GID", "0")
SHEET_SUCURSALES_GID = os.environ.get("SHEET_SUCURSALES_GID")
OUTPUT_FILE = "comercios.json"

if not SHEET_ID:
    print("ERROR: falta la variable SHEET_ID")
    sys.exit(1)

if not SHEET_SUCURSALES_GID:
    print("ERROR: falta SHEET_SUCURSALES_GID (gid de la pestaña Sucursales)")
    sys.exit(1)


def normalizar(texto):
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(texto.split())


ALIASES = {
    "nombre": ["nombre", "comercio", "nombre comercio", "nombre del comercio"],
    "rubro": ["rubro", "categoria"],
    "oferta": ["oferta", "descuento", "promocion"],
    "zona": ["zona", "ubicacion", "direccion"],
    "telefono": ["telefono", "whatsapp", "celular"],
    "imagen": ["imagen", "foto", "url imagen", "url de imagen"],
    "estado": ["estado", "status"],
    "submission_id": ["submission_id"],
}

for numero in range(2, 11):
    ALIASES[f"imagen_{numero}"] = [
        f"imagen_{numero}", f"imagen {numero}", f"foto_{numero}", f"foto {numero}",
    ]


def obtener_valor(fila, campo):
    for alias in ALIASES[campo]:
        key = normalizar(alias)
        if key in fila:
            return fila[key].strip()
    return ""


def obtener_imagenes(fila):
    imagenes = []
    principal = obtener_valor(fila, "imagen")
    if principal:
        imagenes.append(principal)
    for numero in range(2, 11):
        url = obtener_valor(fila, f"imagen_{numero}")
        if url and url not in imagenes:
            imagenes.append(url)
    return imagenes[:10]


def descargar_csv(gid, titulo):
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&gid={gid}"
    )
    print(f"Descargando {titulo} gid={gid}...")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            contenido = response.read().decode("utf-8-sig")
    except Exception as e:
        print(f"ERROR descargando {titulo}: {e}")
        sys.exit(1)

    if "<html" in contenido.lower():
        print(
            f"ERROR: {titulo} devolvió HTML en lugar de CSV. "
            "Verificá el acceso público de lectura de la Sheet."
        )
        sys.exit(1)

    reader = csv.DictReader(io.StringIO(contenido))
    if not reader.fieldnames:
        print(f"ERROR: {titulo} no tiene encabezados")
        sys.exit(1)
    filas = [
        {
            normalizar(k): str(v or "").strip()
            for k, v in raw_row.items() if k
        }
        for raw_row in reader
    ]
    return filas, {normalizar(field) for field in reader.fieldnames if field}


def es_google_maps_url(value):
    try:
        parsed = urlparse(str(value or "").strip())
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    return (
        (host == "maps.app.goo.gl" and len(path) > 1)
        or (host == "goo.gl" and path.startswith("/maps/"))
        or (host in ("google.com", "www.google.com") and path.startswith("/maps"))
        or (host == "maps.google.com" and (len(path) > 1 or bool(parsed.query)))
    )


branch_rows, branch_headers = descargar_csv(SHEET_SUCURSALES_GID, "Sucursales")
required = ("submission_id", "numero", "nombre", "direccion", "google_maps_url")
if any(col not in branch_headers for col in required):
    print("ERROR: la pestaña Sucursales no tiene los encabezados esperados")
    sys.exit(1)

branches_by_submission = {}
for fila in branch_rows:
    submission_id = fila.get("submission_id", "")
    direccion = fila.get("direccion", "")
    if not submission_id or not direccion:
        continue
    try:
        numero = int(fila.get("numero", "0"))
    except ValueError:
        continue
    if not 1 <= numero <= 5:
        continue

    maps_url = fila.get("google_maps_url", "")
    if maps_url and not es_google_maps_url(maps_url):
        print(f"AVISO: enlace de Maps inválido en sucursal {numero}, se omitirá")
        maps_url = ""

    branches_by_submission.setdefault(submission_id, []).append((numero, {
        "nombre": fila.get("nombre", "") or f"Sucursal {numero}",
        "direccion": direccion,
        "google_maps_url": maps_url,
    }))

for submission_id, branches in branches_by_submission.items():
    branches.sort(key=lambda item: item[0])
    # Una sucursal por número; como máximo 5.
    unique = {}
    for numero, branch in branches:
        unique[numero] = branch
    branches_by_submission[submission_id] = list(unique.values())[:5]


rows, _ = descargar_csv(SHEET_GID, "Comercios")
comercios = []
pendientes = 0
rechazados = 0
eliminados = 0
otros = 0

for fila in rows:
    estado = normalizar(obtener_valor(fila, "estado"))
    if estado != "aprobado":
        if estado == "pendiente":
            pendientes += 1
        elif estado == "rechazado":
            rechazados += 1
        elif estado == "eliminado":
            eliminados += 1
        else:
            otros += 1
        continue

    imagenes = obtener_imagenes(fila)
    comercio = {
        "nombre": obtener_valor(fila, "nombre"),
        "rubro": obtener_valor(fila, "rubro"),
        "oferta": obtener_valor(fila, "oferta"),
        "zona": obtener_valor(fila, "zona"),
        "telefono": obtener_valor(fila, "telefono"),
        "imagen": imagenes[0] if imagenes else "",
        "imagenes": imagenes,
    }

    if not comercio["nombre"]:
        continue

    submission_id = obtener_valor(fila, "submission_id")
    if submission_id and submission_id in branches_by_submission:
        comercio["sucursales"] = branches_by_submission[submission_id]

    comercios.append(comercio)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(comercios, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(
    f"OK: {len(comercios)} aprobados publicados. "
    f"{pendientes} pendientes, {rechazados} rechazados, "
    f"{eliminados} eliminados, {otros} sin estado."
)
