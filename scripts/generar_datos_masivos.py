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
# OJO: estas credenciales están a la vista en el código.
# Cámbialas / muévelas a una variable de entorno en cuanto puedas.

MONGO_URI = "mongodb+srv://al222411673_db_user:AccessQR2026@accesoqr.mzgfuac.mongodb.net/accesoqr?retryWrites=true&w=majority&appName=accesoqr"

fake = Faker("es_MX")

client = MongoClient(MONGO_URI)
db = client["accesoqr"]

# Verificamos conexión antes de empezar
try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)


def now_utc():
    """Datetime con zona horaria (utcnow() está deprecado)."""
    return datetime.now(timezone.utc)


# ==========================================
# CANTIDADES (PRUEBA)
# ==========================================

TOTAL_RESIDENTES = 5000
TOTAL_GUARDIAS = 20

TOTAL_VISITAS = 60000

TOTAL_ACCESS_LOGS = 120000

TOTAL_INCIDENCIAS = 8000

BATCH = 1000  # tamaño de lote para insert_many

# ==========================================
# HELPERS
# ==========================================

PRIVADAS = [
    "Cedros",
    "Robles",
    "Sauces",
    "Encinos",
]

MARCAS = [
    "Toyota",
    "Nissan",
    "Honda",
    "Mazda",
    "Volkswagen",
]

MODELOS = [
    "Versa",
    "Yaris",
    "Civic",
    "Mazda3",
    "Jetta",
]

COLORES = [
    "Blanco",
    "Negro",
    "Gris",
    "Rojo",
]

# ==========================================
# ADMIN
# ==========================================

if not db.users.find_one({"rol": "admin"}):
    db.users.insert_one({
        "nombre": "Administrador",
        "correo": "admin@accesoqr.com",
        "password": generate_password_hash("123456"),
        "rol": "admin",
        "estado": "activo",
        "created_at": now_utc(),
    })
    print("Admin creado")

# ==========================================
# GUARDIAS
# ==========================================
# Email único garantizado con índice (evita UniquenessException de faker)

guardias = []

for i in tqdm(range(TOTAL_GUARDIAS), desc="Guardias"):
    guardias.append({
        "nombre": fake.name(),
        "correo": f"guardia{i}_{fake.user_name()}@accesoqr.com",
        "password": generate_password_hash("123456"),
        "rol": "guardia",
        "telefono": fake.msisdn()[:10],
        "estado": "activo",
        "created_at": now_utc(),
    })

if guardias:
    db.users.insert_many(guardias, ordered=False)

print("Guardias creados")

# ==========================================
# RESIDENTES
# ==========================================
# Insertamos por lotes para no cargar 5000 docs de golpe en memoria

residentes = []

for i in tqdm(range(TOTAL_RESIDENTES), desc="Residentes"):
    residentes.append({
        "nombre": fake.name(),
        "correo": f"residente{i}_{fake.user_name()}@accesoqr.com",
        "password": generate_password_hash("123456"),
        "rol": "residente",
        "fraccionamiento": "cedros prueba",
        "privada": random.choice(PRIVADAS),
        "numero_casa": str(random.randint(1, 5000)),
        "telefono": fake.msisdn()[:10],
        "estado": "activo",
        "created_at": now_utc(),
        "ultimo_acceso": now_utc(),
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
    })

    if len(residentes) == BATCH:
        db.users.insert_many(residentes, ordered=False)
        residentes = []

if residentes:
    db.users.insert_many(residentes, ordered=False)

print("Residentes creados")

# ==========================================
# CARGAR USUARIOS
# ==========================================

residentes = list(
    db.users.find({"rol": "residente"})
)

guardias = list(
    db.users.find({"rol": "guardia"})
)

print(f"Residentes: {len(residentes)} | Guardias: {len(guardias)}")

# ==========================================
# VISITS
# ==========================================

visitas = []

for i in tqdm(range(TOTAL_VISITAS), desc="Visitas"):

    residente = random.choice(residentes)

    visita = {
        "residente_id": str(residente["_id"]),
        "residente_nombre": residente["nombre"],
        "telefono_residente": residente["telefono"],

        "nombre_visitante": fake.name(),
        "correo": f"{uuid.uuid4().hex}@accesoqr.com",
        "foto_visitante": {},
        "foto_placa": {},

        "telefono": fake.msisdn()[:10],

        "modalidad_visita": random.choice([
            "temporal",
            "recurrente",
        ]),

        "motivo": random.choice([
            "Familiar",
            "Amigo",
            "Proveedor",
            "Entrega",
        ]),

        "fraccionamiento": residente.get(
            "fraccionamiento",
            "cedros prueba",
        ),

        "condominio": residente.get(
            "privada",
            "Cedros",
        ),

        "residencia_destino": residente["numero_casa"],

        "fecha_visita": fake.date_between(
            start_date="-180d",
            end_date="+30d",
        ).strftime("%Y-%m-%d"),

        "hora_inicio": f"{random.randint(7, 22):02}:{random.randint(0, 59):02}",

        "dias_autorizados": [],

        "hora_programada": None,

        "hora_limite_salida": None,

        "vigencia_desde": None,
        "vigencia_hasta": None,

        "hora_salida": None,
        "fecha_salida": None,

        "entrada_consumida": random.choice([
            True,
            False,
        ]),

        "vehiculo": {
            "placa": fake.bothify("???-###").upper(),
            "marca": random.choice(MARCAS),
            "modelo": random.choice(MODELOS),
            "color": random.choice(COLORES),
        },

        "qr_token": str(uuid.uuid4()),

        "qr_path": f"https://dummy-qr.com/{uuid.uuid4()}.png",

        "qr_estado": random.choice([
            "activo",
            "vencido",
            "cancelado",
        ]),

        "estado": random.choice([
            "activo",
            "finalizado",
        ]),

        "created_at": now_utc(),
    }

    visitas.append(visita)

    if len(visitas) == BATCH:
        db.visits.insert_many(visitas, ordered=False)
        visitas = []

if visitas:
    db.visits.insert_many(visitas, ordered=False)

print("VISITAS CREADAS")

# ==========================================
# RECARGAR VISITAS
# ==========================================

visitas_db = list(
    db.visits.find(
        {},
        {
            "_id": 1,
            "nombre_visitante": 1,
            "residencia_destino": 1,
        },
    )
)

print("Visitas cargadas:", len(visitas_db))

# ==========================================
# ACCESS LOGS
# ==========================================

logs_acceso = []

for i in tqdm(range(TOTAL_ACCESS_LOGS), desc="Access Logs"):

    visita = random.choice(visitas_db)
    guardia = random.choice(guardias)

    logs_acceso.append({
        "visita_id": str(visita["_id"]),
        "guardia_id": str(guardia["_id"]),
        "guardia_nombre": guardia["nombre"],

        "accion": random.choice([
            "entrada",
            "salida",
        ]),

        "fecha_hora": fake.date_time_between(
            start_date="-180d",
            end_date="now",
        ),

        "resultado": random.choice([
            "permitido",
            "rechazado",
        ]),

        "observaciones": random.choice([
            "Entrada autorizada por QR",
            "Salida registrada",
            "QR vencido",
            "QR cancelado",
        ]),
    })

    if len(logs_acceso) == BATCH:
        db.access_logs.insert_many(logs_acceso, ordered=False)
        logs_acceso = []

if logs_acceso:
    db.access_logs.insert_many(logs_acceso, ordered=False)

print("ACCESS LOGS CREADOS")

# ==========================================
# INCIDENCIAS
# ==========================================

incidencias = []

for i in tqdm(range(TOTAL_INCIDENCIAS), desc="Incidencias"):

    visita = random.choice(visitas_db)
    guardia = random.choice(guardias)

    incidencias.append({
        "guardia_id": str(guardia["_id"]),
        "guardia_nombre": guardia["nombre"],

        "tipo_incidencia": random.choice([
            "qr_no_valido",
            "placa_no_coincide",
            "sin_autorizacion",
            "persona_sospechosa",
        ]),

        "descripcion": fake.sentence(),

        "estado": random.choice([
            "abierta",
            "cerrada",
        ]),

        "fecha_hora": fake.date_time_between(
            start_date="-180d",
            end_date="now",
        ),

        "visita_id": str(visita["_id"]),
        "visitante": visita["nombre_visitante"],
        "residencia_destino": visita["residencia_destino"],
    })

    if len(incidencias) == BATCH:
        db.incidencias.insert_many(incidencias, ordered=False)
        incidencias = []

if incidencias:
    db.incidencias.insert_many(incidencias, ordered=False)

print("INCIDENCIAS CREADAS")

print("\n¡LISTO! Datos de prueba generados correctamente.")