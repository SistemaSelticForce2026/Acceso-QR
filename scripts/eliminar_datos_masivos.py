"""
eliminar_datos_masivos.py
Elimina SOLO los datos de PRUEBA de AccesoQR, INCLUYENDO sus fotos/QR en Cloudinary.
NUNCA borra datos reales. Archivo único: ya incluye lo de eliminar_datos_masivos_fotos.py.

    python scripts\\eliminar_datos_masivos.py

Cómo distingue lo falso de lo real:
  - Datos de prueba: tienen el campo es_prueba = True (lo pone el generador).
    Como respaldo, también detecta los del seed viejo (qr_path dummy-qr.com
    y correos residenteN_...), por si quedaron en la BD.
  - Logs/incidencias de prueba: solo los que apuntan a visitas de prueba.
  - Fotos/QR de prueba: viven en TUS mismas carpetas (accesoqr/...) pero su
    public_id empieza con "seed_". Se borran (a) las referenciadas por las
    visitas de prueba y (b) un barrido de lo que empiece con "seed_".

Conserva admin, guardias, visitas reales y TUS fotos reales (las reales NO
empiezan con "seed_", así que el barrido jamás las toca).
"""

import os

import cloudinary
import cloudinary.api
from dotenv import load_dotenv
from pymongo import MongoClient

# ==========================================
# CONFIG
# ==========================================

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

CONFIRMAR = True  # pide escribir SI antes de borrar
BARRIDO_POR_PREFIJO = True  # además, barre lo que empiece con seed_ (orphans)

# Las fotos de prueba viven en TUS carpetas reales, pero su public_id empieza
# con "seed_". Barremos SOLO esos prefijos -> nunca toca tus fotos reales.
PREFIJOS_PRUEBA = [
    "accesoqr/visitantes/seed_",
    "accesoqr/placas/seed_",
    "accesoqr/qr/seed_",
    "accesoqr_seed/",
]

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK\n")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)

CLOUDINARY_OK = bool(cloudinary.config().cloud_name)
if not CLOUDINARY_OK:
    print(
        "AVISO: faltan credenciales de Cloudinary (.env). "
        "Se borrará Mongo pero NO las fotos.\n"
    )

# ==========================================
# FILTROS (solo datos de prueba)
# ==========================================

FILTRO_VISITAS_PRUEBA = {
    "$or": [
        {"es_prueba": True},
        {"qr_path": {"$regex": "dummy-qr.com"}},  # respaldo: seed viejo
    ]
}
FILTRO_RESIDENTES_PRUEBA = {
    "rol": "residente",
    "$or": [
        {"es_prueba": True},
        {"correo": {"$regex": r"^residente\d+_"}},  # respaldo: seed viejo
    ],
}

# ==========================================
# 1) Recolectar IDs y public_ids ANTES de borrar nada
# ==========================================

ids_prueba = []
public_ids = set()

for v in db.visits.find(
    FILTRO_VISITAS_PRUEBA,
    {
        "_id": 1,
        "foto_visitante.public_id": 1,
        "foto_placa.public_id": 1,
        "qr_public_id": 1,
    },
):
    ids_prueba.append(str(v["_id"]))
    for campo in ("foto_visitante", "foto_placa"):
        foto = v.get(campo)
        if isinstance(foto, dict) and foto.get("public_id"):
            public_ids.add(foto["public_id"])
    if v.get("qr_public_id"):
        public_ids.add(v["qr_public_id"])

visitas_prueba = len(ids_prueba)
visitas_reales = db.visits.estimated_document_count() - visitas_prueba
residentes_prueba = db.users.count_documents(FILTRO_RESIDENTES_PRUEBA)

print("Se BORRARÁN (prueba):")
print(f"  visitas de prueba    : {visitas_prueba}")
print(f"  residentes de prueba : {residentes_prueba}")
print(f"  fotos/QR Cloudinary  : {len(public_ids)} (referenciados por las visitas)")
print(f"  + sus access_logs e incidencias relacionados")
print("Se CONSERVAN:")
print(f"  visitas REALES       : {visitas_reales}")
print(f"  admin y guardias\n")

if visitas_reales > 0:
    print(">> OJO: hay visitas que NO son de prueba. Esas NO se tocarán. <<\n")

if CONFIRMAR:
    resp = input("Escribe SI para borrar SOLO los datos de prueba: ").strip().upper()
    if resp != "SI":
        print("Cancelado. No se borró nada.")
        raise SystemExit(0)

# ==========================================
# 2) Borrar fotos de Cloudinary
# ==========================================


def chunk(lista, n):
    for i in range(0, len(lista), n):
        yield lista[i : i + n]


if CLOUDINARY_OK:
    # 2a) Borrado dirigido: exactamente las referenciadas (lotes de 100)
    ids = list(public_ids)
    borradas = 0
    for lote in chunk(ids, 100):
        try:
            resp = cloudinary.api.delete_resources(lote, resource_type="image")
            borradas += sum(
                1 for estado in resp.get("deleted", {}).values() if estado == "deleted"
            )
        except Exception as e:
            print(f"  error borrando un lote de fotos: {e}")
    print(f"Fotos borradas de Cloudinary (referenciadas): {borradas}")

    # 2b) Barrido por prefijo "seed_": limpia orphans de corridas previas.
    #     SOLO borra lo que empieza con seed_ dentro de tus carpetas, así que
    #     nunca toca tus fotos reales (que NO empiezan con seed_).
    if BARRIDO_POR_PREFIJO:
        total_barrido = 0
        for prefijo in PREFIJOS_PRUEBA:
            for _ in range(100):  # tope; borra hasta 1000 por vuelta
                try:
                    resp = cloudinary.api.delete_resources_by_prefix(
                        prefijo, resource_type="image"
                    )
                except Exception as e:
                    print(f"  barrido '{prefijo}': {e}")
                    break
                n = sum(1 for s in resp.get("deleted", {}).values() if s == "deleted")
                total_barrido += n
                if n == 0:
                    break
        if total_barrido:
            print(f"Fotos borradas de Cloudinary (barrido seed_): {total_barrido}")
        # Solo intentamos quitar la carpeta legada (esa sí es exclusiva de prueba).
        # NO borramos accesoqr/visitantes|placas|código QR porque son tuyas/reales.
        for sub in (
            "accesoqr_seed/visitantes",
            "accesoqr_seed/placas",
            "accesoqr_seed/qr",
            "accesoqr_seed",
        ):
            try:
                cloudinary.api.delete_folder(sub)
            except Exception:
                pass

# ==========================================
# 3) Borrar logs e incidencias de esas visitas
# ==========================================


def borrar_por_visita(coleccion, ids):
    total = 0
    for lote in chunk(ids, 5000):
        r = coleccion.delete_many({"visita_id": {"$in": lote}})
        total += r.deleted_count
    return total


if ids_prueba:
    n_logs = borrar_por_visita(db.access_logs, ids_prueba)
    print(f"Access logs de prueba borrados: {n_logs}")
    n_inc = borrar_por_visita(db.incidencias, ids_prueba)
    print(f"Incidencias de prueba borradas: {n_inc}")

# ==========================================
# 4) Borrar visitas de prueba
# ==========================================

r = db.visits.delete_many(FILTRO_VISITAS_PRUEBA)
print(f"Visitas de prueba borradas: {r.deleted_count}")

# ==========================================
# 5) Borrar residentes de prueba
# ==========================================

r = db.users.delete_many(FILTRO_RESIDENTES_PRUEBA)
print(f"Residentes de prueba borrados: {r.deleted_count}")

print("\nListo. Se eliminaron datos de prueba y sus fotos. Lo real quedó intacto.")
