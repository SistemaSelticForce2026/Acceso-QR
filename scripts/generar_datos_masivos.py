"""
Seed de datos de prueba para AccesoQR  (versión optimizada)

Cambios clave:
  1. La contraseña se hashea UNA sola vez (antes: 5020 veces -> ~8 min perdidos).
  2. No se vuelve a consultar la BD: se reutilizan los _id que devuelve insert_many.
  3. Se crean índices al final -> el panel admin consulta rápido y no satura RAM.
  4. NO recrea admin ni guardias si ya existen (la limpieza masiva se hace con
     limpiar_accesoqr.py, que conserva admin y guardias).
"""

from pymongo import MongoClient
from faker import Faker
from werkzeug.security import generate_password_hash
from tqdm import tqdm
from datetime import datetime, timezone
import random
import uuid

# ==========================================
# CONFIG
# ==========================================

MONGO_URI = "mongodb+srv://al222411673_db_user:AccessQR2026@accesoqr.mzgfuac.mongodb.net/accesoqr?retryWrites=true&w=majority&appName=accesoqr"

fake = Faker("es_MX")
client = MongoClient(MONGO_URI)
db = client["accesoqr"]

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)


def now_utc():
    return datetime.now(timezone.utc)


# Se calcula UNA sola vez. Este es el ahorro más grande del script.
PASSWORD_HASH = generate_password_hash("123456")

# ==========================================
# CANTIDADES
# ==========================================

TOTAL_RESIDENTES = 5000
TOTAL_GUARDIAS = 20

TOTAL_VISITAS = 20000
TOTAL_ACCESS_LOGS = 40000
TOTAL_INCIDENCIAS = 4000

BATCH = 5000

# ==========================================
# CATÁLOGOS
# ==========================================

PRIVADAS = ["Cedros", "Robles", "Sauces", "Encinos"]
MARCAS = ["Toyota", "Nissan", "Honda", "Mazda", "Volkswagen"]
MODELOS = ["Versa", "Yaris", "Civic", "Mazda3", "Jetta"]
COLORES = ["Blanco", "Negro", "Gris", "Rojo"]
MOTIVOS = ["Familiar", "Amigo", "Proveedor", "Entrega"]
ACCIONES = ["entrada", "salida"]
RESULTADOS = ["permitido", "rechazado"]
OBS = ["Entrada autorizada por QR", "Salida registrada", "QR vencido", "QR cancelado"]
TIPOS_INC = [
    "qr_no_valido",
    "placa_no_coincide",
    "sin_autorizacion",
    "persona_sospechosa",
]

# ==========================================
# ADMIN  (solo si no existe)
# ==========================================

if not db.users.find_one({"rol": "admin"}):
    db.users.insert_one(
        {
            "nombre": "Administrador",
            "correo": "admin@accesoqr.com",
            "password": PASSWORD_HASH,
            "rol": "admin",
            "estado": "activo",
            "created_at": now_utc(),
        }
    )
    print("Admin creado")
else:
    print("Admin ya existe, no se recrea")

# ==========================================
# GUARDIAS  (solo si no hay ninguno)
# ==========================================

if db.users.count_documents({"rol": "guardia"}) == 0:
    guardias_docs, guardias_meta = [], []
    for i in range(TOTAL_GUARDIAS):
        nombre = fake.name()
        guardias_docs.append(
            {
                "nombre": nombre,
                "correo": f"guardia{i}_{fake.user_name()}@accesoqr.com",
                "password": PASSWORD_HASH,
                "rol": "guardia",
                "telefono": fake.msisdn()[:10],
                "estado": "activo",
                "created_at": now_utc(),
            }
        )
        guardias_meta.append(nombre)

    res = db.users.insert_many(guardias_docs, ordered=False)
    guardias_ref = [
        {"_id": _id, "nombre": n} for _id, n in zip(res.inserted_ids, guardias_meta)
    ]
    print("Guardias creados")
else:
    # Ya existen: solo los cargamos para usarlos en logs/incidencias
    guardias_ref = [
        {"_id": g["_id"], "nombre": g["nombre"]}
        for g in db.users.find({"rol": "guardia"}, {"nombre": 1})
    ]
    print(f"Guardias ya existen ({len(guardias_ref)}), no se recrean")

# ==========================================
# RESIDENTES  (sin re-consultar: usamos los _id devueltos)
# ==========================================

residentes_ref = []
buf_docs, buf_meta = [], []

for i in tqdm(range(TOTAL_RESIDENTES), desc="Residentes"):
    nombre = fake.name()
    privada = random.choice(PRIVADAS)
    casa = str(random.randint(1, 5000))
    tel = fake.msisdn()[:10]

    buf_docs.append(
        {
            "nombre": nombre,
            "correo": f"residente{i}_{fake.user_name()}_{uuid.uuid4().hex[:6]}@accesoqr.com",
            "password": PASSWORD_HASH,
            "rol": "residente",
            "fraccionamiento": "cedros prueba",
            "privada": privada,
            "numero_casa": casa,
            "telefono": tel,
            "estado": "activo",
            "created_at": now_utc(),
            "ultimo_acceso": now_utc(),
            "intentos_fallidos": 0,
            "bloqueado_hasta": None,
        }
    )
    buf_meta.append(
        {
            "nombre": nombre,
            "telefono": tel,
            "numero_casa": casa,
            "privada": privada,
            "fraccionamiento": "cedros prueba",
        }
    )

    if len(buf_docs) == BATCH:
        r = db.users.insert_many(buf_docs, ordered=False)
        for _id, m in zip(r.inserted_ids, buf_meta):
            m["_id"] = _id
            residentes_ref.append(m)
        buf_docs, buf_meta = [], []

if buf_docs:
    r = db.users.insert_many(buf_docs, ordered=False)
    for _id, m in zip(r.inserted_ids, buf_meta):
        m["_id"] = _id
        residentes_ref.append(m)

print(f"Residentes creados: {len(residentes_ref)}")

# ==========================================
# VISITS  (guardamos ref liviana para logs/incidencias)
# ==========================================

visitas_ref = []
buf_docs, buf_meta = [], []

for i in tqdm(range(TOTAL_VISITAS), desc="Visitas"):
    residente = random.choice(residentes_ref)
    nombre_vis = fake.name()

    buf_docs.append(
        {
            "residente_id": str(residente["_id"]),
            "residente_nombre": residente["nombre"],
            "telefono_residente": residente["telefono"],
            "nombre_visitante": nombre_vis,
            "correo": f"{uuid.uuid4().hex}@accesoqr.com",
            "foto_visitante": {},
            "foto_placa": {},
            "telefono": fake.msisdn()[:10],
            "modalidad_visita": random.choice(["temporal", "recurrente"]),
            "motivo": random.choice(MOTIVOS),
            "fraccionamiento": residente["fraccionamiento"],
            "condominio": residente["privada"],
            "residencia_destino": residente["numero_casa"],
            "fecha_visita": fake.date_between(
                start_date="-180d", end_date="+30d"
            ).strftime("%Y-%m-%d"),
            "hora_inicio": f"{random.randint(7, 22):02}:{random.randint(0, 59):02}",
            "dias_autorizados": [],
            "hora_programada": None,
            "hora_limite_salida": None,
            "vigencia_desde": None,
            "vigencia_hasta": None,
            "hora_salida": None,
            "fecha_salida": None,
            "entrada_consumida": random.choice([True, False]),
            "vehiculo": {
                "placa": fake.bothify("???-###").upper(),
                "marca": random.choice(MARCAS),
                "modelo": random.choice(MODELOS),
                "color": random.choice(COLORES),
            },
            "qr_token": str(uuid.uuid4()),
            "qr_path": f"https://dummy-qr.com/{uuid.uuid4()}.png",
            "qr_estado": random.choice(["activo", "vencido", "cancelado"]),
            "estado": random.choice(["activo", "finalizado"]),
            "created_at": now_utc(),
        }
    )
    buf_meta.append(
        {"nombre_visitante": nombre_vis, "residencia_destino": residente["numero_casa"]}
    )

    if len(buf_docs) == BATCH:
        r = db.visits.insert_many(buf_docs, ordered=False)
        for _id, m in zip(r.inserted_ids, buf_meta):
            m["_id"] = _id
            visitas_ref.append(m)
        buf_docs, buf_meta = [], []

if buf_docs:
    r = db.visits.insert_many(buf_docs, ordered=False)
    for _id, m in zip(r.inserted_ids, buf_meta):
        m["_id"] = _id
        visitas_ref.append(m)

print(f"Visitas creadas: {len(visitas_ref)}")

# ==========================================
# ACCESS LOGS
# ==========================================

buf = []
for i in tqdm(range(TOTAL_ACCESS_LOGS), desc="Access Logs"):
    visita = random.choice(visitas_ref)
    guardia = random.choice(guardias_ref)
    buf.append(
        {
            "visita_id": str(visita["_id"]),
            "guardia_id": str(guardia["_id"]),
            "guardia_nombre": guardia["nombre"],
            "accion": random.choice(ACCIONES),
            "fecha_hora": fake.date_time_between(start_date="-180d", end_date="now"),
            "resultado": random.choice(RESULTADOS),
            "observaciones": random.choice(OBS),
        }
    )
    if len(buf) == BATCH:
        db.access_logs.insert_many(buf, ordered=False)
        buf = []
if buf:
    db.access_logs.insert_many(buf, ordered=False)
print("Access logs creados")

# ==========================================
# INCIDENCIAS
# ==========================================

buf = []
for i in tqdm(range(TOTAL_INCIDENCIAS), desc="Incidencias"):
    visita = random.choice(visitas_ref)
    guardia = random.choice(guardias_ref)
    buf.append(
        {
            "guardia_id": str(guardia["_id"]),
            "guardia_nombre": guardia["nombre"],
            "tipo_incidencia": random.choice(TIPOS_INC),
            "descripcion": fake.sentence(),
            "estado": random.choice(["abierta", "cerrada"]),
            "fecha_hora": fake.date_time_between(start_date="-180d", end_date="now"),
            "visita_id": str(visita["_id"]),
            "visitante": visita["nombre_visitante"],
            "residencia_destino": visita["residencia_destino"],
        }
    )
    if len(buf) == BATCH:
        db.incidencias.insert_many(buf, ordered=False)
        buf = []
if buf:
    db.incidencias.insert_many(buf, ordered=False)
print("Incidencias creadas")

# ==========================================
# ÍNDICES  (crear solo si no existen, para no fallar al re-ejecutar)
# ==========================================

print("Creando índices...")
db.users.create_index("rol")
db.users.create_index("correo", unique=True)
db.users.create_index("estado")

db.visits.create_index("residente_id")

try:
    db.visits.drop_index("qr_token_1")
except Exception:
    pass

db.visits.create_index("qr_token", unique=True)

db.visits.create_index("estado")
db.visits.create_index([("created_at", -1)])
db.visits.create_index("fecha_visita")

db.access_logs.create_index("visita_id")
db.access_logs.create_index("guardia_id")
db.access_logs.create_index([("fecha_hora", -1)])

db.incidencias.create_index("estado")
db.incidencias.create_index("visita_id")
db.incidencias.create_index([("fecha_hora", -1)])
print("Índices listos")

print("\n¡LISTO! Datos de prueba generados correctamente.")
