"""
eliminar_datos_masivos.py
Elimina SOLO datos de PRUEBA en AccesoQR (MULTI-FRACCIONAMIENTO),
incluyendo fotos/QR en Cloudinary.

NUNCA borra datos reales.

Limpieza de Cloudinary en DOS pasadas (complementarias):
  1. Por documento: borra las fotos referenciadas por las visitas de prueba.
  2. Por prefijo 'seed_': barre las carpetas del generador para eliminar
     cualquier imagen huérfana (p. ej. de una corrida del generador que se
     interrumpió antes de insertar las visitas). Es lo que hace que NO queden
     imágenes de prueba consumiendo tu plan de Cloudinary.
"""

import sys
import os
import re
import unicodedata

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import cloudinary
import cloudinary.api
from dotenv import load_dotenv
from pymongo import MongoClient

from utils.fraccionamientos import (
    FRACCIONAMIENTOS,
    VISITAS_COLECCIONES,
    RESIDENTES_COLECCIONES,
    _norm,
)

# =========================================================
# CONFIG
# =========================================================

MONGO_URI = "mongodb+srv://software_db_user:M22TlbYUEJCo7lXh@accesoqr.zopq4ja.mongodb.net/?appName=accesoqr"

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

client = MongoClient(MONGO_URI)
db = client["accesoqr"]

CONFIRMAR = True

# =========================================================
# CLOUDINARY: estructura de carpetas/prefijo (igual que el generador)
# =========================================================

PREFIJO_PRUEBA = "seed_"
TIPOS_FOTOS = ["visitantes", "placas", "qr"]


def slug_cloudinary(texto):
    texto = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )
    texto = texto.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def carpeta_cloudinary(fraccionamiento, tipo):
    return f"accesoqr/{slug_cloudinary(fraccionamiento)}/{tipo}"


# =========================================================
# FILTROS PRUEBA
# =========================================================

FILTRO_VISITAS_PRUEBA = {
    "$or": [
        {"es_prueba": True},
        {"qr_path": {"$regex": "dummy-qr.com"}},
    ]
}

FILTRO_RESIDENTES_PRUEBA = {
    "$or": [
        {"es_prueba": True},
        {"correo": {"$regex": r"^residente\d+_"}},
    ]
}

# =========================================================
# CONEXIÓN
# =========================================================

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK\n")
except Exception as e:
    print("Error MongoDB:", e)
    raise SystemExit(1)

# =========================================================
# RECOLECTAR DATOS
# =========================================================

ids_visitas = []
public_ids = set()

for frac in FRACCIONAMIENTOS:
    key = _norm(frac)
    col = VISITAS_COLECCIONES[key]

    for v in db[col].find(
        FILTRO_VISITAS_PRUEBA,
        {
            "_id": 1,
            "foto_visitante.public_id": 1,
            "foto_placa.public_id": 1,
            "qr_public_id": 1,
        },
    ):
        ids_visitas.append(str(v["_id"]))

        for campo in ("foto_visitante", "foto_placa"):
            foto = v.get(campo)
            if isinstance(foto, dict) and foto.get("public_id"):
                public_ids.add(foto["public_id"])

        if v.get("qr_public_id"):
            public_ids.add(v["qr_public_id"])

print("\nRESUMEN:")
print(f"Visitas de prueba: {len(ids_visitas)}")
print(f"Fotos/QR referenciadas a borrar: {len(public_ids)}")

if CONFIRMAR:
    resp = input("\nEscribe SI para borrar TODO lo de prueba: ").strip().upper()
    if resp != "SI":
        print("Cancelado.")
        raise SystemExit(0)

# =========================================================
# CLOUDINARY
# =========================================================


def chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def borrar_por_prefijo(prefijo):
    """Borra todos los recursos cuyo public_id empiece con 'prefijo'.
    Repite mientras Cloudinary marque la respuesta como parcial."""
    total = 0
    while True:
        try:
            resp = cloudinary.api.delete_resources_by_prefix(
                prefijo, resource_type="image"
            )
        except Exception as e:
            print(f"  Error Cloudinary ({prefijo}): {e}")
            break
        total += sum(1 for x in resp.get("deleted", {}).values() if x == "deleted")
        if not resp.get("partial"):
            break
    return total


# --- Pasada 1: borrar las fotos referenciadas por las visitas de prueba ---
if public_ids:
    borradas = 0
    for lote in chunk(list(public_ids), 100):
        try:
            resp = cloudinary.api.delete_resources(lote, resource_type="image")
            borradas += sum(
                1 for x in resp.get("deleted", {}).values() if x == "deleted"
            )
        except Exception as e:
            print("Error Cloudinary:", e)
    print(f"Fotos borradas (referenciadas): {borradas}")

# --- Pasada 2: barrer por prefijo 'seed_' para no dejar imágenes huérfanas ---
print("\nLimpieza por prefijo 'seed_' en las carpetas del generador...")
extra = 0
for frac in FRACCIONAMIENTOS:
    for tipo in TIPOS_FOTOS:
        prefijo = f"{carpeta_cloudinary(frac, tipo)}/{PREFIJO_PRUEBA}"
        extra += borrar_por_prefijo(prefijo)
print(f"Imágenes 'seed_' adicionales borradas: {extra}")

# =========================================================
# LOGS + INCIDENCIAS
# =========================================================

if ids_visitas:

    def borrar_visitas_relacionadas():
        total = 0
        for lote in chunk(ids_visitas, 5000):
            r = db.access_logs.delete_many({"visita_id": {"$in": lote}})
            total += r.deleted_count
        return total

    def borrar_incidencias_relacionadas():
        total = 0
        for lote in chunk(ids_visitas, 5000):
            r = db.incidencias.delete_many({"visita_id": {"$in": lote}})
            total += r.deleted_count
        return total

    print("\nAccess logs:", borrar_visitas_relacionadas())
    print("Incidencias:", borrar_incidencias_relacionadas())

# =========================================================
# BORRAR VISITAS Y RESIDENTES
# =========================================================

for frac in FRACCIONAMIENTOS:
    key = _norm(frac)

    col_v = VISITAS_COLECCIONES[key]
    col_r = RESIDENTES_COLECCIONES[key]

    r1 = db[col_v].delete_many(FILTRO_VISITAS_PRUEBA)
    r2 = db[col_r].delete_many(FILTRO_RESIDENTES_PRUEBA)

    print(f"{frac} -> visitas: {r1.deleted_count} | residentes: {r2.deleted_count}")

print("\nLISTO: se eliminaron SOLO datos de prueba.")
