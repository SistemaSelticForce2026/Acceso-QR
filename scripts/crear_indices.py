"""
Crea SOLO los índices de AccesoQR. No genera ni borra datos.
Es idempotente: si un índice ya existe (aunque sea con otras opciones),
lo deja como está y sigue, sin tronar.

    python scripts\crear_indices.py
"""

from pymongo import MongoClient
from pymongo.errors import OperationFailure

MONGO_URI = "mongodb+srv://software_db_user:M22TlbYUEJCo7lXh@accesoqr.zopq4ja.mongodb.net/?appName=accesoqr"

client = MongoClient(MONGO_URI)
db = client["accesoqr"]

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK\n")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)


def idx(coleccion, llave, **opts):
    """Crea el índice. Si ya existe o hay conflicto de nombre, lo deja y sigue."""
    try:
        nombre = coleccion.create_index(llave, **opts)
        print(f"  OK   {coleccion.name}: {nombre}")
    except OperationFailure:
        print(f"  SKIP {coleccion.name}: {llave} ya existe (se deja como está)")


print("Creando índices...\n")

# users
idx(db.users, "rol")
idx(db.users, "correo", unique=True)
idx(db.users, "estado")

# visits
idx(db.visits, "residente_id")
idx(db.visits, "qr_token")  # sin unique: ya existe uno creado por la app
idx(db.visits, "estado")
idx(db.visits, [("created_at", -1)])
idx(db.visits, "fecha_visita")

# access_logs
idx(db.access_logs, "visita_id")
idx(db.access_logs, "guardia_id")
idx(db.access_logs, [("fecha_hora", -1)])

# incidencias
idx(db.incidencias, "estado")
idx(db.incidencias, "visita_id")
idx(db.incidencias, [("fecha_hora", -1)])

print("\nListo. Índices revisados/creados.")
