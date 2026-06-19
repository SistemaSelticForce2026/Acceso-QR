"""
eliminar_datos_masivos.py
Elimina SOLO datos de PRUEBA en AccesoQR (MULTI-FRACCIONAMIENTO),
incluyendo fotos/QR en Cloudinary.

NUNCA borra datos reales.
"""

import sys
import os

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
print(f"Fotos/QR a borrar: {len(public_ids)}")

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

    print(f"Fotos borradas: {borradas}")

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

    print("Access logs:", borrar_visitas_relacionadas())
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
