"""
generar_datos_masivos.py
Genera datos de PRUEBA para AccesoQR, repartidos en los 3 FRACCIONAMIENTOS
(cada uno con su propia colección de residentes y de visitas), con fotos
(visitante + placa + QR) en Cloudinary.

CÓMO USAR (3 pasos):
  1. Ten tu .env con CLOUDINARY_CLOUD_NAME / API_KEY / API_SECRET.
  2. pip install pymongo faker werkzeug tqdm pillow qrcode cloudinary python-dotenv
  3. python scripts\\generar_datos_masivos.py

Dónde caen los datos:
  - Residentes -> residentes_foresta_dream_lagons / _cedro_zinacantepec / _villas_del_bosque_ii
  - Visitas    -> visitas_foresta_dream_lagons / _cedro_zinacantepec / _villas_del_bosque_ii
  - Admin y guardias -> users (NO se parten)
  - access_logs e incidencias -> sin cambios

Cómo se marca lo de prueba:
  - En Mongo: cada residente/visita lleva es_prueba = True.
  - En Cloudinary: public_id empieza con "seed_".

NOVEDADES de esta versión:
  - fecha_visita repartida del 1-ene-2025 al 31-dic-2026 (pasado, hoy y futuro).
  - Estados realistas: activo / dentro / salida_registrada, con tiempos de
    entrada y salida coherentes con la fecha de la visita.
  - Un porcentaje de visitas "incompletas" (sin foto, sin vehículo, sin
    teléfono; recurrentes sin días ni horario) para ver cómo se comporta el
    panel con datos vacíos.
"""

import io
import os
import random
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta, date

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
# FRACCIONAMIENTOS  (deben coincidir con utils/fraccionamientos.py)
# Se guardan en MINÚSCULAS, igual que el registro de la app.
# ==========================================

FRACCIONAMIENTOS = [
    "foresta dream lagons",
    "cedro zinacantepec",
    "villas del bosque ii",
]

RES_COL = {
    "foresta dream lagons": "residentes_foresta_dream_lagons",
    "cedro zinacantepec": "residentes_cedro_zinacantepec",
    "villas del bosque ii": "residentes_villas_del_bosque_ii",
}

VIS_COL = {
    "foresta dream lagons": "visitas_foresta_dream_lagons",
    "cedro zinacantepec": "visitas_cedro_zinacantepec",
    "villas del bosque ii": "visitas_villas_del_bosque_ii",
}

# ==========================================
# PANEL DE CONTROL
# ==========================================

PRUEBA_RAPIDA = False

TOTAL_RESIDENTES = 5000
TOTAL_GUARDIAS = 20
TOTAL_VISITAS = 20000
TOTAL_ACCESS_LOGS = 40000
TOTAL_INCIDENCIAS = 4000

BATCH = 5000

if PRUEBA_RAPIDA:
    TOTAL_RESIDENTES = 60
    TOTAL_GUARDIAS = 5
    TOTAL_VISITAS = 240
    TOTAL_ACCESS_LOGS = 300
    TOTAL_INCIDENCIAS = 40
    BATCH = 500
    print(">> MODO PRUEBA RÁPIDA: generando pocos datos <<\n")

# ==========================================
# RANGO DE FECHAS Y COMPORTAMIENTO DE LOS DATOS
# ==========================================

# Las visitas se reparten en TODO este rango (pasado, hoy y futuro).
FECHA_VISITA_INICIO = date(2025, 1, 1)
FECHA_VISITA_FIN = date(2026, 12, 31)
HOY = date.today()

# Los registros históricos (logs / incidencias) sí son del pasado: del inicio
# del rango hasta "ahora".
INICIO_HISTORICO = datetime(2025, 1, 1)

# Proporción de visitas "que no tienen nada" (sin foto / vehículo / teléfono;
# recurrentes sin días ni horario). Sirve para ver el panel con datos vacíos.
PROB_INCOMPLETA = 0.18

# Mezcla temporal vs recurrente (más temporales, como en la vida real).
PESOS_MODALIDAD = {"temporal": 7, "recurrente": 3}

# ==========================================
# CONFIG DE FOTOS
# ==========================================

PLAN_CREDITOS = 25
TOPE_CREDITOS_SUBIDA = PLAN_CREDITOS * 0.5

MODO_FOTOS = "pool"

POOL_VISITANTES = 20 if PRUEBA_RAPIDA else 100
POOL_PLACAS = 20 if PRUEBA_RAPIDA else 100
POOL_QR = 20 if PRUEBA_RAPIDA else 100
HILOS_SUBIDA = 8

THUMB_WIDTH = 150


PREFIJO_PRUEBA = "seed_"

import re
import unicodedata


def slug_cloudinary(texto):
    texto = (
        unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    )

    texto = texto.lower().strip()

    return re.sub(r"[^a-z0-9]+", "_", texto).strip("_")


def carpeta_cloudinary(fraccionamiento, tipo):
    return f"accesoqr/" f"{slug_cloudinary(fraccionamiento)}/" f"{tipo}"


# ==========================================
# CATÁLOGOS
# ==========================================

PRIVADAS = ["cedros", "robles", "sauces", "encinos"]
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

# Catálogos para las visitas RECURRENTES (coinciden con la plantilla del panel)
TIPOS_RECURRENTE = [
    "domestica",
    "jardinero",
    "mantenimiento",
    "proveedor",
    "chofer",
    "familiar",
    "otro",
]
DIAS_SEMANA = [
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
]
HORARIOS_PRESET = [
    ("07:00", "15:00"),
    ("08:00", "18:00"),
    ("09:00", "14:00"),
    ("00:00", "23:59"),  # sin restricción
]

# ==========================================
# HELPERS DE ESTADO / TIEMPOS COHERENTES
# ==========================================


def _dt(fecha, hhmm):
    """datetime (naive) combinando una fecha date + 'HH:MM'."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(fecha.year, fecha.month, fecha.day, h, m)


def estado_visita(modalidad, fv_date, hora_inicio):
    """Devuelve estado / qr_estado / tiempos de entrada-salida coherentes con
    la fecha de la visita, para que el dashboard se vea como uso real:

    - Futuro  -> agendada (activo), sin entrada.
    - Hoy     -> mezcla: dentro / salió / aún por llegar.
    - Pasado  -> casi todas entraron y salieron; algunas no se presentaron o
                 quedaron canceladas/vencidas.
    - Recurrente -> pase vigente (activo); de vez en cuando alguien dentro.
    """
    base = {
        "estado": "activo",
        "qr_estado": "activo",
        "entrada_consumida": False,
        "hora_entrada_real": None,
        "fecha_entrada_real": None,
        "hora_salida": None,
        "fecha_salida": None,
    }

    if modalidad == "recurrente":
        if random.random() < 0.10:  # alguien dentro ahora mismo
            hi = hora_inicio or "08:00"
            base.update(
                estado="dentro",
                entrada_consumida=True,
                hora_entrada_real=hi,
                fecha_entrada_real=_dt(HOY, hi),
            )
        base["qr_estado"] = random.choices(["activo", "vencido"], weights=[8, 2])[0]
        return base

    # ---- Temporal ----
    if fv_date is None:
        return base

    hora_inicio = hora_inicio or "10:00"
    entrada_dt = _dt(fv_date, hora_inicio)

    if fv_date > HOY:  # agendada a futuro
        return base

    if fv_date == HOY:  # hoy: estado variado
        r = random.random()
        if r < 0.45:
            base.update(
                estado="dentro",
                entrada_consumida=True,
                hora_entrada_real=hora_inicio,
                fecha_entrada_real=entrada_dt,
            )
        elif r < 0.85:
            salida_dt = entrada_dt + timedelta(hours=random.randint(1, 4))
            base.update(
                estado="salida_registrada",
                qr_estado="finalizado",
                entrada_consumida=True,
                hora_entrada_real=hora_inicio,
                fecha_entrada_real=entrada_dt,
                hora_salida=salida_dt.strftime("%H:%M:%S"),
                fecha_salida=salida_dt,
            )
        # else -> sigue "activo" (aún por llegar)
        return base

    # ---- Pasada ----
    r = random.random()
    if r < 0.75:  # entró y salió ese día
        salida_dt = entrada_dt + timedelta(hours=random.randint(1, 5))
        base.update(
            estado="salida_registrada",
            qr_estado="finalizado",
            entrada_consumida=True,
            hora_entrada_real=hora_inicio,
            fecha_entrada_real=entrada_dt,
            hora_salida=salida_dt.strftime("%H:%M:%S"),
            fecha_salida=salida_dt,
        )
    elif r < 0.90:  # no se presentó
        base.update(estado="activo", qr_estado="vencido")
    else:  # cancelada
        base.update(estado="activo", qr_estado="cancelado")
    return base


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
    transf = n_subidas / 1000.0
    storage = (n_subidas * kb_prom) / (1024 * 1024)
    return transf, storage


def subir_visitante(i, fraccionamiento):
    genero = random.choice(["men", "women"])
    idx = random.randint(0, 99)
    url = f"https://randomuser.me/api/portraits/{genero}/{idx}.jpg"
    res = cloudinary.uploader.upload(
        url,
        folder=carpeta_cloudinary(fraccionamiento, "visitantes"),
        public_id=f"{PREFIJO_PRUEBA}v_{i}",
        overwrite=True,
        resource_type="image",
    )
    return _ref_cloudinary(res)


def subir_placa(i, fraccionamiento, texto=None):
    texto = texto or fake.bothify("???-###").upper()
    buf = generar_imagen_placa(texto)
    res = cloudinary.uploader.upload(
        buf,
        folder=carpeta_cloudinary(fraccionamiento, "placas"),
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


def subir_qr(i, fraccionamiento, data=None):

    data = data or f"https://accesoqr.com/v/{uuid.uuid4()}"
    buf = generar_imagen_qr(data)
    res = cloudinary.uploader.upload(
        buf,
        folder=carpeta_cloudinary(fraccionamiento, "qr"),
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
# RESIDENTES  (repartidos en los 3 fraccionamientos)
# ==========================================

residentes_ref = []
res_buffers = {col: [] for col in RES_COL.values()}
res_metas = {col: [] for col in RES_COL.values()}


def flush_residentes(col):
    if res_buffers[col]:
        r = db[col].insert_many(res_buffers[col], ordered=False)
        for _id, m in zip(r.inserted_ids, res_metas[col]):
            m["_id"] = _id
            residentes_ref.append(m)
        res_buffers[col] = []
        res_metas[col] = []


for i in tqdm(range(TOTAL_RESIDENTES), desc="Residentes"):
    nombre = fake.name()
    frac = random.choice(FRACCIONAMIENTOS)  # minúsculas
    col = RES_COL[frac]
    privada = random.choice(PRIVADAS)
    casa = str(random.randint(1, 5000))
    tel = fake.msisdn()[:10]

    res_buffers[col].append(
        {
            "nombre": nombre,
            "correo": f"residente{i}_{fake.user_name()}_{uuid.uuid4().hex[:6]}@accesoqr.com",
            "password": PASSWORD_HASH,
            "rol": "residente",
            "fraccionamiento": frac,
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
    res_metas[col].append(
        {
            "nombre": nombre,
            "telefono": tel,
            "numero_casa": casa,
            "privada": privada,
            "fraccionamiento": frac,
        }
    )

    if len(res_buffers[col]) >= BATCH:
        flush_residentes(col)

for col in RES_COL.values():
    flush_residentes(col)

print(f"Residentes creados: {len(residentes_ref)}")

# ==========================================
# POOL DE FOTOS
# ==========================================

pool_visitantes = {}
pool_placas = {}
pool_qr = {}

if MODO_FOTOS == "pool":
    n_subidas = len(FRACCIONAMIENTOS) * (POOL_VISITANTES + POOL_PLACAS + POOL_QR)


elif MODO_FOTOS == "unico":
    n_subidas = TOTAL_VISITAS * 3
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
    for frac in FRACCIONAMIENTOS:

        print(f"\nCreando pool para {frac}")

        pool_visitantes[frac] = construir_pool(
            lambda i, f=frac: subir_visitante(i, f),
            POOL_VISITANTES,
            f"Visitantes {frac}",
        )

        pool_placas[frac] = construir_pool(
            lambda i, f=frac: subir_placa(i, f), POOL_PLACAS, f"Placas {frac}"
        )

        pool_qr[frac] = construir_pool(
            lambda i, f=frac: subir_qr(i, f), POOL_QR, f"QR {frac}"
        )

    for frac in FRACCIONAMIENTOS:
        print(
            f"{frac}: "
            f"{len(pool_visitantes[frac])} visitantes, "
            f"{len(pool_placas[frac])} placas, "
            f"{len(pool_qr[frac])} qr"
        )
elif MODO_FOTOS == "unico":
    print("MODO_FOTOS = 'unico': se subirá 1 imagen por visita.")


def obtener_assets(i, fraccionamiento, placa_texto, qr_data):
    if MODO_FOTOS == "pool":
        return (
            random.choice(pool_visitantes[fraccionamiento]),
            random.choice(pool_placas[fraccionamiento]),
            random.choice(pool_qr[fraccionamiento]),
        )
    if MODO_FOTOS == "unico":
        uid = uuid.uuid4().hex[:10]
        return (
            subir_visitante(f"u_{uid}", fraccionamiento),
            subir_placa(f"u_{uid}", fraccionamiento, placa_texto),
            subir_qr(f"u_{uid}", fraccionamiento, qr_data),
        )
    return {}, {}, {}


# ==========================================
# VISITS  (cada una en la colección de su fraccionamiento)
# ==========================================

visitas_ref = []
vis_buffers = {col: [] for col in VIS_COL.values()}
vis_metas = {col: [] for col in VIS_COL.values()}


def flush_visitas(col):
    if vis_buffers[col]:
        r = db[col].insert_many(vis_buffers[col], ordered=False)
        for _id, m in zip(r.inserted_ids, vis_metas[col]):
            m["_id"] = _id
            visitas_ref.append(m)
        vis_buffers[col] = []
        vis_metas[col] = []


_modalidades = list(PESOS_MODALIDAD.keys())
_pesos_modalidad = list(PESOS_MODALIDAD.values())

for i in tqdm(range(TOTAL_VISITAS), desc="Visitas"):
    residente = random.choice(residentes_ref)
    frac = residente["fraccionamiento"]
    col = VIS_COL[frac]

    nombre_vis = fake.name()
    placa_texto = fake.bothify("???-###").upper()
    qr_token = str(uuid.uuid4())
    foto_visitante, foto_placa, qr_ref = obtener_assets(
        i, frac, placa_texto, f"https://accesoqr.com/v/{qr_token}"
    )

    modalidad = random.choices(_modalidades, weights=_pesos_modalidad)[0]
    incompleta = random.random() < PROB_INCOMPLETA

    # Las temporales tienen fecha fija (repartida en todo el rango); las
    # recurrentes normalmente NO tienen una fecha concreta.
    if modalidad == "temporal":
        fv_date = fake.date_between_dates(FECHA_VISITA_INICIO, FECHA_VISITA_FIN)
        fecha_visita = fv_date.strftime("%Y-%m-%d")
        hora_inicio = f"{random.randint(7, 22):02}:{random.randint(0, 59):02}"
    else:
        fv_date = None
        fecha_visita = None
        hora_inicio = None

    st = estado_visita(modalidad, fv_date, hora_inicio)

    doc = {
        "residente_id": str(residente["_id"]),
        "residente_nombre": residente["nombre"],
        "telefono_residente": residente["telefono"],
        "nombre_visitante": nombre_vis,
        "correo": f"{uuid.uuid4().hex}@accesoqr.com",
        "foto_visitante": foto_visitante,
        "foto_placa": foto_placa,
        "telefono": fake.msisdn()[:10],
        "modalidad_visita": modalidad,
        "motivo": random.choice(MOTIVOS),
        "fraccionamiento": frac,
        "condominio": residente["privada"],
        "residencia_destino": residente["numero_casa"],
        "fecha_visita": fecha_visita,
        "hora_inicio": hora_inicio,
        "dias_autorizados": [],
        "hora_programada": None,
        "hora_limite_salida": None,
        "vigencia_desde": None,
        "vigencia_hasta": None,
        "vehiculo": {
            "placa": placa_texto,
            "marca": random.choice(MARCAS),
            "modelo": random.choice(MODELOS),
            "color": random.choice(COLORES),
        },
        "qr_token": qr_token,
        "qr_path": (qr_ref or {}).get("url"),
        "qr_public_id": (qr_ref or {}).get("public_id"),
        "created_at": now_utc(),
        "es_prueba": True,
        # estado + tiempos coherentes con la fecha
        **st,
    }

    # Recurrentes "completas": días, horario, tipo y vigencia (lo que muestra
    # el panel en sus chips).
    if modalidad == "recurrente" and not incompleta:
        vig_ini = fake.date_between_dates(FECHA_VISITA_INICIO, HOY)
        vig_fin = fake.date_between_dates(HOY, FECHA_VISITA_FIN)
        h_ini, h_fin = random.choice(HORARIOS_PRESET)
        doc.update(
            {
                "tipo_recurrente": random.choice(TIPOS_RECURRENTE),
                "dias": random.sample(DIAS_SEMANA, k=random.randint(1, 5)),
                "hora_desde": h_ini,
                "hora_hasta": h_fin,
                "fecha_inicio_recurrente": vig_ini.strftime("%Y-%m-%d"),
                "fecha_fin_recurrente": vig_fin.strftime("%Y-%m-%d"),
            }
        )

    # Visitas "que no tienen nada" -> para ver cómo se comporta el panel con
    # información incompleta (sin foto, sin vehículo, sin teléfono; recurrentes
    # sin días ni horario).
    if incompleta:
        doc["foto_visitante"] = None
        doc["foto_placa"] = None
        doc["vehiculo"] = None
        doc["telefono"] = None
        if modalidad == "recurrente":
            doc["dias"] = []
            doc["dias_autorizados"] = []

    vis_buffers[col].append(doc)
    vis_metas[col].append(
        {"nombre_visitante": nombre_vis, "residencia_destino": residente["numero_casa"]}
    )

    if len(vis_buffers[col]) >= BATCH:
        flush_visitas(col)

for col in VIS_COL.values():
    flush_visitas(col)

print(f"Visitas creadas: {len(visitas_ref)}")

# ==========================================
# ACCESS LOGS  (repartidos del inicio del rango hasta hoy)
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
            "fecha_hora": fake.date_time_between(
                start_date=INICIO_HISTORICO, end_date="now"
            ),
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
# INCIDENCIAS  (repartidas del inicio del rango hasta hoy)
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
            "fecha_hora": fake.date_time_between(
                start_date=INICIO_HISTORICO, end_date="now"
            ),
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
# ÍNDICES  (sobre las colecciones nuevas)
# ==========================================

print("Creando índices...")

db.users.create_index("rol")
db.users.create_index("correo", unique=True)
db.users.create_index("estado")

for col in RES_COL.values():
    db[col].create_index("correo", unique=True)
    db[col].create_index("estado")
    db[col].create_index([("fraccionamiento", 1), ("privada", 1), ("numero_casa", 1)])

for col in VIS_COL.values():
    try:
        db[col].drop_index("qr_token_1")
    except Exception:
        pass
    db[col].create_index("qr_token", unique=True)
    db[col].create_index("residente_id")
    db[col].create_index("estado")
    db[col].create_index([("created_at", -1)])
    db[col].create_index("fecha_visita")
    # Compuestos que aceleran la agenda/historial y los conteos del panel.
    db[col].create_index([("fecha_visita", 1), ("estado", 1)])
    db[col].create_index([("modalidad_visita", 1), ("fecha_visita", 1)])
    db[col].create_index([("estado", 1), ("fecha_salida", -1)])

db.access_logs.create_index("visita_id")
db.access_logs.create_index("guardia_id")
db.access_logs.create_index([("fecha_hora", -1)])

db.incidencias.create_index("estado")
db.incidencias.create_index("visita_id")
db.incidencias.create_index([("fecha_hora", -1)])
print("Índices listos")

# Resumen por fraccionamiento
print("\nResumen por fraccionamiento:")
for frac in FRACCIONAMIENTOS:
    nr = db[RES_COL[frac]].count_documents({})
    nv = db[VIS_COL[frac]].count_documents({})
    print(f"  {frac:22s} -> residentes: {nr:5d} | visitas: {nv:6d}")

# Resumen de estados (para confirmar que el panel tendrá de todo)
print("\nResumen de estados de visitas (todos los fraccionamientos):")
_estados = {}
for col in VIS_COL.values():
    for r in db[col].aggregate([{"$group": {"_id": "$estado", "n": {"$sum": 1}}}]):
        _estados[r["_id"]] = _estados.get(r["_id"], 0) + r["n"]
for est, n in sorted(_estados.items(), key=lambda x: -x[1]):
    print(f"  {str(est):20s} -> {n}")

print("\n¡LISTO! Datos de prueba generados y repartidos en los 3 fraccionamientos.")
