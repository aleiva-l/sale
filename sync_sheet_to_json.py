import csv
import io
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse

SHEET_ID = os.environ.get("SHEET_ID")
SHEET_GID = os.environ.get("SHEET_GID", "0")
SHEET_SUCURSALES_GID = os.environ.get("SHEET_SUCURSALES_GID")
OUTPUT_FILE = "comercios.json"


def normalizar(texto):
    texto = str(texto or "").strip().lower()
    return " ".join("".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).split())


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
        if normalizar(alias) in fila:
            return fila[normalizar(alias)].strip()
    return ""


def obtener_imagenes(fila):
    imagenes = []
    for campo in ["imagen", *[f"imagen_{i}" for i in range(2, 11)]]:
        valor = obtener_valor(fila, campo)
        if valor and valor not in imagenes:
            imagenes.append(valor)
    return imagenes[:10]


def descargar_csv(gid, titulo):
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
    print(f"Descargando {titulo} gid={gid}...")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        contenido = response.read().decode("utf-8-sig")
    if "<html" in contenido.lower():
        raise ValueError(f"{titulo} devolvió HTML. Verificá el acceso público de lectura.")
    reader = csv.DictReader(io.StringIO(contenido))
    if not reader.fieldnames:
        raise ValueError(f"{titulo} no tiene encabezados")
    filas = [
        {normalizar(k): str(v or "").strip() for k, v in row.items() if k}
        for row in reader
    ]
    return filas, {normalizar(field) for field in reader.fieldnames if field}


def es_google_maps_url(value):
    try:
        parsed = urlparse(str(value or "").strip())
        host = (parsed.hostname or "").lower()
    except ValueError:
        return False
    path = parsed.path or ""
    return parsed.scheme == "https" and (
        (host == "maps.app.goo.gl" and len(path) > 1)
        or (host == "goo.gl" and path.startswith("/maps/"))
        or (host in ("google.com", "www.google.com") and path.startswith("/maps"))
        or (host == "maps.google.com" and (len(path) > 1 or bool(parsed.query)))
    )


def coordenadas_validas(latitud, longitud):
    if latitud is None or longitud is None:
        return None
    if str(latitud).strip() == "" or str(longitud).strip() == "":
        return None
    try:
        lat = float(str(latitud).strip().replace(",", "."))
        lon = float(str(longitud).strip().replace(",", "."))
    except ValueError:
        return None
    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return {"latitud": lat, "longitud": lon}
    return None


def coordenadas_maps(url):
    # Extraer solo el punto del lugar o una consulta numérica explícita.
    # @lat,long puede ser el centro de la cámara y se omite.
    if not es_google_maps_url(url):
        return None
    texto = unquote(url)
    punto = re.search(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", texto)
    if punto:
        return coordenadas_validas(*punto.groups())
    query = parse_qs(urlparse(url).query)
    for campo in ("query", "q"):
        valor = query.get(campo, [""])[0]
        punto = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*", valor)
        if punto:
            return coordenadas_validas(*punto.groups())
    return None


def ejecutar():
    if not SHEET_ID or not SHEET_SUCURSALES_GID:
        raise ValueError("Falta SHEET_ID o SHEET_SUCURSALES_GID")
    branch_rows, headers = descargar_csv(SHEET_SUCURSALES_GID, "Sucursales")
    required = ("submission_id", "numero", "nombre", "direccion", "google_maps_url")
    if any(col not in headers for col in required):
        raise ValueError("Sucursales no tiene los encabezados esperados")
    branches_by_submission = {}
    for fila in branch_rows:
        sid, direccion = fila.get("submission_id", ""), fila.get("direccion", "")
        if not sid or not direccion:
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
        branch = {
            "nombre": fila.get("nombre", "") or f"Sucursal {numero}",
            "direccion": direccion,
            "google_maps_url": maps_url,
        }
        lat, lon = fila.get("latitud", ""), fila.get("longitud", "")
        if lat.strip() or lon.strip():
            coords = coordenadas_validas(lat, lon)
            if coords is None:
                print(f"AVISO: coordenadas inválidas en {sid}, sucursal {numero}; se omiten")
        else:
            coords = coordenadas_maps(maps_url)
        if coords:
            branch.update(coords)
        branches_by_submission.setdefault(sid, []).append((numero, branch))

    for sid, branches in branches_by_submission.items():
        unique = {}
        for numero, branch in sorted(branches, key=lambda item: item[0]):
            unique[numero] = branch
        branches_by_submission[sid] = list(unique.values())[:5]

    rows, _ = descargar_csv(SHEET_GID, "Comercios")
    comercios = []
    estados = {"pendiente": 0, "rechazado": 0, "eliminado": 0, "otros": 0}
    for fila in rows:
        estado = normalizar(obtener_valor(fila, "estado"))
        if estado != "aprobado":
            estados[estado if estado in estados else "otros"] += 1
            continue
        imagenes = obtener_imagenes(fila)
        comercio = {campo: obtener_valor(fila, campo) for campo in
                    ("nombre", "rubro", "oferta", "zona", "telefono")}
        comercio.update(imagen=imagenes[0] if imagenes else "", imagenes=imagenes)
        if not comercio["nombre"]:
            continue
        sid = obtener_valor(fila, "submission_id")
        if sid in branches_by_submission:
            comercio["sucursales"] = branches_by_submission[sid]
        comercios.append(comercio)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(comercios, file, ensure_ascii=False, indent=2)
        file.write("\n")
    print(f"OK: {len(comercios)} aprobados publicados. Otros estados: {estados}")


if __name__ == "__main__":
    try:
        ejecutar()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
