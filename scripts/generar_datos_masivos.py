"""
generar_datos_masivos.py
Genera datos de PRUEBA para AccesoQR, con fotos (visitante + placa + QR) en Cloudinary.
Archivo único: ya incluye lo que antes estaba en generar_datos_masivos_fotos.py.

CÓMO USAR (3 pasos):
  1. Ten tu .env con CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET.
  2. pip install pymongo faker werkzeug tqdm pillow qrcode cloudinary python-dotenv
  3. python scripts\\generar_datos_masivos.py

LO ÚNICO QUE SUELES TOCAR está abajo en "PANEL DE CONTROL":
  - PRUEBA_RAPIDA = True  -> genera poquitos datos para verificar que todo jala.
  - PRUEBA_RAPIDA = False -> los números reales (5000 residentes, 20000 visitas...).
  - MODO_FOTOS = "pool"   -> recomendado (sube ~300 imágenes y las reparte).

Scripts hermanos:
  - repartir_fechas_visitas.py -> reparte las fechas en 180 días.
  - eliminar_datos_masivos.py  -> borra SOLO lo de prueba (Mongo + Cloudinary).

Cómo se marca lo de prueba:
  - En Mongo: cada residente/visita lleva es_prueba = True.
  - En Cloudinary: las fotos se suben a TUS MISMAS carpetas (accesoqr/visitantes,
    accesoqr/placas, accesoqr/código QR) pero su public_id empieza con "seed_".
    Ese prefijo permite borrarlas sin tocar tus fotos reales (no se crea otra carpeta).
"""

import io
import os
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from faker import Faker
import qrcode
from PIL import Image, ImageDraw, ImageFont
from pymongo import MongoClient
from tqdm import tqdm
from werkzeug.security import generate_password_hash

# ==========================================
# CONFIG
# ==========================================

# OJO: estas credenciales quedaron expuestas en texto. Cuando termines de
# probar, conviene rotar la contraseña de Mongo y mover esto a variables
# de entorno (.env), no dejarlo hardcodeado.
MONGO_URI = "mongodb+srv://software_db_user:M22TlbYUEJCo7lXh@accesoqr.zopq4ja.mongodb.net/?appName=accesoqr"

load_dotenv()
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

if not cloudinary.config().cloud_name:
    print(
        "Faltan las variables de Cloudinary (.env). Revisa "
        "CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET."
    )
    raise SystemExit(1)

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


PASSWORD_HASH = generate_password_hash("123456")

# ==========================================
# PANEL DE CONTROL  (lo que normalmente tocas)
# ==========================================

# True  = pocos datos, para comprobar en segundos que todo funciona.
# False = los números reales de abajo.
PRUEBA_RAPIDA = False

# Cantidades reales
TOTAL_RESIDENTES = 5000
TOTAL_GUARDIAS = 20
TOTAL_VISITAS = 20000
TOTAL_ACCESS_LOGS = 40000
TOTAL_INCIDENCIAS = 4000

BATCH = 5000

# Si activas la prueba rápida, se ignoran los números de arriba.
if PRUEBA_RAPIDA:
    TOTAL_RESIDENTES = 50
    TOTAL_GUARDIAS = 5
    TOTAL_VISITAS = 200
    TOTAL_ACCESS_LOGS = 300
    TOTAL_INCIDENCIAS = 40
    BATCH = 500
    print(">> MODO PRUEBA RÁPIDA: generando pocos datos <<\n")

# ==========================================
# CONFIG DE FOTOS
# ==========================================

# --- Presupuesto Cloudinary (plan gratis) -------------------------------
# 1 crédito = 1,000 transformaciones = 1 GB storage = 1 GB ancho de banda.
# SUBIR cada imagen cuenta como 1 transformación.
# Bajar desde una URL remota (randomuser) NO gasta ancho de banda.
# Tienes 25 créditos. Este seed debe gastar fracciones de crédito.
PLAN_CREDITOS = 25
TOPE_CREDITOS_SUBIDA = PLAN_CREDITOS * 0.5  # no gastar más del 50% subiendo

# "pool"  -> sube un set chico y lo reparte (RECOMENDADO; gasta ~0.2 créditos).
# "unico" -> 1 imagen por visita (~40k subidas = ~40 créditos = NO cabe en gratis).
MODO_FOTOS = "pool"

POOL_VISITANTES = 20 if PRUEBA_RAPIDA else 100  # retratos (randomuser ~200 únicos)
POOL_PLACAS = 20 if PRUEBA_RAPIDA else 100  # placas (generadas, únicas)
POOL_QR = 20 if PRUEBA_RAPIDA else 100  # QRs (generados, únicos)
HILOS_SUBIDA = 8  # subidas en paralelo (no lo subas mucho por rate limit)

# Tamaño de entrega para el panel: en lugar de la imagen completa, sirve un
# thumbnail (w_150, formato y calidad automáticos). Pesa ~5-15 KB y se cachea,
# así casi no gastas ancho de banda al listar miles de visitas.
THUMB_WIDTH = 150

# Carpetas: las MISMAS que ya usa tu app (no se crea otra carpeta).
CARPETA_BASE = "accesoqr"
CARPETA_VISITANTES = f"{CARPETA_BASE}/visitantes"
CARPETA_PLACAS = f"{CARPETA_BASE}/placas"
CARPETA_QR = f"{CARPETA_BASE}/qr"

# Prefijo en el public_id para distinguir lo de prueba de lo real DENTRO de las
# mismas carpetas. El borrado solo elimina lo que empieza con esto.
PREFIJO_PRUEBA = "seed_"

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
# HELPERS DE FOTOS
# ==========================================


def _cargar_fuente(size):
    for ruta in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arialbd.ttf",
    ]:
        try:
            return ImageFont.truetype(ruta, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generar_imagen_placa(texto, w=640, h=320):
    """Genera una imagen tipo placa MX (en memoria) con el texto dado."""
    img = Image.new("RGB", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, w - 7, h - 7], outline="#1B1B1B", width=8)
    d.rectangle([16, 16, w - 17, 74], fill="#0B6623")
    d.text((w / 2, 45), "MEXICO", font=_cargar_fuente(34), fill="white", anchor="mm")

    size = 150
    while size > 20:
        f = _cargar_fuente(size)
        if d.textlength(texto, font=f) <= w - 80:
            break
        size -= 4
    d.text(
        (w / 2, h / 2 + 35),
        texto,
        font=_cargar_fuente(size),
        fill="#101010",
        anchor="mm",
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _ref_cloudinary(res):
    """Lo que se guarda en Mongo. Ajusta las llaves a como lo lee tu app
    (por ej. si tu template usa foto_visitante.url o .secure_url).
    thumb_url es una versión chica para listados (ahorra ancho de banda)."""
    thumb_url = cloudinary.CloudinaryImage(res["public_id"]).build_url(
        width=THUMB_WIDTH, crop="fill", fetch_format="auto", quality="auto", secure=True
    )
    return {
        "public_id": res["public_id"],
        "url": res["secure_url"],
        "secure_url": res["secure_url"],
        "thumb_url": thumb_url,
        "width": res.get("width"),
        "height": res.get("height"),
        "format": res.get("format"),
    }


def estimar_creditos(n_subidas, kb_prom=40):
    """Estimación rápida de créditos: subir = 1 transformación c/u + storage."""
    transf = n_subidas / 1000.0
    storage = (n_subidas * kb_prom) / (1024 * 1024)  # GB
    return transf, storage


def subir_visitante(i):
    genero = random.choice(["men", "women"])
    idx = random.randint(0, 99)
    url = f"https://randomuser.me/api/portraits/{genero}/{idx}.jpg"
    res = cloudinary.uploader.upload(
        url,
        folder=CARPETA_VISITANTES,
        public_id=f"{PREFIJO_PRUEBA}v_{i}",
        overwrite=True,
        resource_type="image",
    )
    return _ref_cloudinary(res)


def subir_placa(i, texto=None):
    texto = texto or fake.bothify("???-###").upper()
    buf = generar_imagen_placa(texto)
    res = cloudinary.uploader.upload(
        buf,
        folder=CARPETA_PLACAS,
        public_id=f"{PREFIJO_PRUEBA}p_{i}",
        overwrite=True,
        resource_type="image",
    )
    return _ref_cloudinary(res)


def generar_imagen_qr(data):
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def subir_qr(i, data=None):
    data = data or f"https://accesoqr.com/v/{uuid.uuid4()}"
    buf = generar_imagen_qr(data)
    res = cloudinary.uploader.upload(
        buf,
        folder=CARPETA_QR,
        public_id=f"{PREFIJO_PRUEBA}qr_{i}",
        overwrite=True,
        resource_type="image",
    )
    return _ref_cloudinary(res)


def construir_pool(fn, n, desc):
    pool = [None] * n
    with ThreadPoolExecutor(max_workers=HILOS_SUBIDA) as ex:
        futs = {ex.submit(fn, i): i for i in range(n)}
        for fut in tqdm(as_completed(futs), total=n, desc=desc):
            i = futs[fut]
            try:
                pool[i] = fut.result()
            except Exception as e:
                print(f"  fallo subiendo {desc} #{i}: {e}")
    return [p for p in pool if p]


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
    guardias_ref = [
        {"_id": g["_id"], "nombre": g["nombre"]}
        for g in db.users.find({"rol": "guardia"}, {"nombre": 1})
    ]
    print(f"Guardias ya existen ({len(guardias_ref)}), no se recrean")

# ==========================================
# RESIDENTES
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
            "es_prueba": True,
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
# POOL DE FOTOS (si MODO_FOTOS == "pool")
# ==========================================

pool_visitantes, pool_placas, pool_qr = [], [], []

# --- Chequeo de presupuesto antes de subir nada ---
if MODO_FOTOS == "pool":
    n_subidas = POOL_VISITANTES + POOL_PLACAS + POOL_QR
elif MODO_FOTOS == "unico":
    n_subidas = TOTAL_VISITAS * 3  # visitante + placa + qr por visita
else:
    n_subidas = 0

if n_subidas:
    transf, storage = estimar_creditos(n_subidas)
    print(
        f"\nEstimado Cloudinary: {n_subidas} subidas "
        f"~ {transf:.2f} créditos de transformación + {storage:.3f} GB storage"
    )
    print(
        f"(tienes {PLAN_CREDITOS} créditos; tope de seguridad para subir: "
        f"{TOPE_CREDITOS_SUBIDA:.0f})"
    )
    if transf + storage > TOPE_CREDITOS_SUBIDA:
        print("\nABORTADO: esto gastaría demasiado de tu plan gratis.")
        print("Usa MODO_FOTOS = 'pool', o baja TOTAL_VISITAS / los tamaños de pool.")
        raise SystemExit(1)

if MODO_FOTOS == "pool":
    print(
        f"Subiendo pool de fotos a Cloudinary "
        f"({POOL_VISITANTES} visitantes + {POOL_PLACAS} placas + {POOL_QR} QR)..."
    )
    pool_visitantes = construir_pool(
        subir_visitante, POOL_VISITANTES, "Pool visitantes"
    )
    pool_placas = construir_pool(subir_placa, POOL_PLACAS, "Pool placas")
    pool_qr = construir_pool(subir_qr, POOL_QR, "Pool QR")
    if not pool_visitantes or not pool_placas or not pool_qr:
        print("No se pudo armar el pool de fotos. Revisa Cloudinary/internet.")
        raise SystemExit(1)
    print(
        f"Pool listo: {len(pool_visitantes)} visitantes, "
        f"{len(pool_placas)} placas, {len(pool_qr)} QR"
    )
elif MODO_FOTOS == "unico":
    print("MODO_FOTOS = 'unico': se subirá 1 imagen por visita.")


def obtener_assets(i, placa_texto, qr_data):
    """Devuelve (foto_visitante, foto_placa, qr_ref) según el modo elegido."""
    if MODO_FOTOS == "pool":
        return (
            random.choice(pool_visitantes),
            random.choice(pool_placas),
            random.choice(pool_qr),
        )
    if MODO_FOTOS == "unico":
        uid = uuid.uuid4().hex[:10]
        return (
            subir_visitante(f"u_{uid}"),
            subir_placa(f"u_{uid}", placa_texto),
            subir_qr(f"u_{uid}", qr_data),
        )
    return {}, {}, {}


# ==========================================
# VISITS
# ==========================================

visitas_ref = []
buf_docs, buf_meta = [], []

for i in tqdm(range(TOTAL_VISITAS), desc="Visitas"):
    residente = random.choice(residentes_ref)
    nombre_vis = fake.name()
    placa_texto = fake.bothify("???-###").upper()
    qr_token = str(uuid.uuid4())
    foto_visitante, foto_placa, qr_ref = obtener_assets(
        i, placa_texto, f"https://accesoqr.com/v/{qr_token}"
    )

    buf_docs.append(
        {
            "residente_id": str(residente["_id"]),
            "residente_nombre": residente["nombre"],
            "telefono_residente": residente["telefono"],
            "nombre_visitante": nombre_vis,
            "correo": f"{uuid.uuid4().hex}@accesoqr.com",
            "foto_visitante": foto_visitante,
            "foto_placa": foto_placa,
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
                "placa": placa_texto,
                "marca": random.choice(MARCAS),
                "modelo": random.choice(MODELOS),
                "color": random.choice(COLORES),
            },
            "qr_token": qr_token,
            # QR real en Cloudinary. qr_path = URL (como tu app); guardamos
            # también qr_public_id para poder borrarlo después.
            "qr_path": (qr_ref or {}).get("url"),
            "qr_public_id": (qr_ref or {}).get("public_id"),
            "qr_estado": random.choice(["activo", "vencido", "cancelado"]),
            "estado": random.choice(["activo", "finalizado"]),
            "created_at": now_utc(),
            "es_prueba": True,
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
# ÍNDICES
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
