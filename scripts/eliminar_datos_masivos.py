"""
Elimina SOLO los datos de PRUEBA de AccesoQR (los generados por el seed).
NUNCA borra datos reales.

    python scripts\eliminar_datos_masivos.py

Cómo distingue lo falso de lo real:
  - Visitas de prueba: su qr_path contiene "dummy-qr.com" (las reales no).
  - Residentes de prueba: su correo es del tipo residente0_xxx_abc123@accesoqr.com
  - Logs/incidencias de prueba: solo los que apuntan a visitas de prueba.

Conserva admin y guardias.
"""

import re
from pymongo import MongoClient

MONGO_URI = "mongodb+srv://al222411673_db_user:AccessQR2026@accesoqr.mzgfuac.mongodb.net/accesoqr?retryWrites=true&w=majority&appName=accesoqr"

client = MongoClient(MONGO_URI)
db = client["accesoqr"]

CONFIRMAR = True  # pide escribir SI antes de borrar

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK\n")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)

# Filtros que identifican SOLO datos de prueba
FILTRO_VISITAS_PRUEBA = {"qr_path": {"$regex": "dummy-qr.com"}}
FILTRO_RESIDENTES_PRUEBA = {"rol": "residente",
                            "correo": {"$regex": r"^residente\d+_"}}

# Conteo previo (para que veas qué se va a borrar y qué se conserva)
visitas_prueba = db.visits.count_documents(FILTRO_VISITAS_PRUEBA)
visitas_reales = db.visits.estimated_document_count() - visitas_prueba
residentes_prueba = db.users.count_documents(FILTRO_RESIDENTES_PRUEBA)

print("Se BORRARÁN (prueba):")
print(f"  visitas de prueba   : {visitas_prueba}")
print(f"  residentes de prueba: {residentes_prueba}")
print(f"  + sus access_logs e incidencias relacionados")
print("Se CONSERVAN:")
print(f"  visitas REALES      : {visitas_reales}")
print(f"  admin y guardias\n")

if visitas_reales > 0:
    print(">> OJO: hay visitas que NO son de prueba. Esas NO se tocarán. <<\n")

if CONFIRMAR:
    resp = input("Escribe SI para borrar SOLO los datos de prueba: ").strip().upper()
    if resp != "SI":
        print("Cancelado. No se borró nada.")
        raise SystemExit(0)

# 1) IDs de las visitas de prueba (para borrar sus logs/incidencias)
ids_prueba = [str(v["_id"]) for v in db.visits.find(FILTRO_VISITAS_PRUEBA, {"_id": 1})]

def borrar_por_visita(coleccion, ids):
    """Borra en lotes los docs cuyo visita_id esté en la lista de prueba."""
    total = 0
    for i in range(0, len(ids), 5000):
        lote = ids[i:i + 5000]
        r = coleccion.delete_many({"visita_id": {"$in": lote}})
        total += r.deleted_count
    return total

if ids_prueba:
    n_logs = borrar_por_visita(db.access_logs, ids_prueba)
    print(f"Access logs de prueba borrados: {n_logs}")
    n_inc = borrar_por_visita(db.incidencias, ids_prueba)
    print(f"Incidencias de prueba borradas: {n_inc}")

# 2) Visitas de prueba
r = db.visits.delete_many(FILTRO_VISITAS_PRUEBA)
print(f"Visitas de prueba borradas: {r.deleted_count}")

# 3) Residentes de prueba
r = db.users.delete_many(FILTRO_RESIDENTES_PRUEBA)
print(f"Residentes de prueba borrados: {r.deleted_count}")

print("\nListo. Solo se eliminaron datos de prueba. Los reales quedaron intactos.")