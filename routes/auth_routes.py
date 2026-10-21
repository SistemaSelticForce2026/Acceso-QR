"""Rutas de autenticación: login, captcha, recuperación/cambio de contraseña y logout.

Las cuentas de residentes y guardias las da de alta el administrador.
"""

import hashlib
import hmac
import io
import random
from datetime import datetime, timedelta

from bson import ObjectId
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import mongo
from utils.fraccionamientos import (
    buscar_login,
    coleccion_residentes,
)

# ==================
# BLUEPRINT AUTH
# ==================

auth_bp = Blueprint("auth", __name__)

# Captcha sensible a mayúsculas/minúsculas. Se excluyen los caracteres que se
# ven igual en ambos casos (c, o, s, v, w, x, z) y los confusables
# (i, l, I, O, 0, 1).
CAPTCHA_MAYUS = "ABDEFGHJKLMNPQRTUY"
CAPTCHA_MINUS = "abdefghjkmnpqrtuy"
CAPTCHA_DIGITOS = "23456789"

# ================
# INICIO
# ================


@auth_bp.route("/")
def index():
    """Redirige la raíz del sitio a la pantalla de login."""

    return redirect(url_for("auth.login"))


# =======================
# CAPTCHA (imagen)
# =======================


def _hash_captcha(texto):
    """Devuelve un HMAC del captcha para no guardar el texto plano en la cookie."""

    clave = current_app.secret_key
    if isinstance(clave, str):
        clave = clave.encode("utf-8")
    return hmac.new(clave, texto.encode("utf-8"), hashlib.sha256).hexdigest()


def _cargar_fuente(tamano=30):
    """Intenta cargar una fuente TrueType; si no existe, usa la de Pillow."""

    for nombre in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tamano)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


@auth_bp.route("/captcha.png")
def captcha_img():
    """Genera una imagen de captcha y guarda SOLO su hash en la sesión."""

    rnd = random.SystemRandom()

    # Siempre 2 mayúsculas + 2 minúsculas + 1 número, en orden aleatorio
    caracteres = (
        [rnd.choice(CAPTCHA_MAYUS) for _ in range(2)]
        + [rnd.choice(CAPTCHA_MINUS) for _ in range(2)]
        + [rnd.choice(CAPTCHA_DIGITOS)]
    )
    rnd.shuffle(caracteres)
    texto = "".join(caracteres)

    session["captcha"] = _hash_captcha(texto)

    # Descomenta SOLO para probar; vuelve a comentarla después.
    # current_app.logger.warning("CAPTCHA: %s", texto)

    w, h = 170, 52
    img = Image.new("RGB", (w, h), (246, 247, 249))
    d = ImageDraw.Draw(img)
    font = _cargar_fuente(30)

    # Ruido: líneas y puntos
    for _ in range(5):
        d.line(
            [
                (rnd.randint(0, w), rnd.randint(0, h)),
                (rnd.randint(0, w), rnd.randint(0, h)),
            ],
            fill=(rnd.randint(150, 200),) * 3,
            width=1,
        )
    for _ in range(120):
        d.point(
            (rnd.randint(0, w), rnd.randint(0, h)),
            fill=(rnd.randint(120, 200),) * 3,
        )

    # Letras con posición variable
    for i, ch in enumerate(texto):
        x = 14 + i * 30 + rnd.randint(-3, 3)
        y = rnd.randint(4, 12)
        d.text(
            (x, y),
            ch,
            font=font,
            fill=(rnd.randint(20, 70), rnd.randint(40, 90), rnd.randint(110, 190)),
        )

    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)

    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


# ============
# LOGIN
# ============


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Autentica al usuario, gestiona bloqueos por intentos y crea la sesión."""

    if request.method == "POST":

        # ===============
        # VALIDAR CAPTCHA
        # ===============
        # Sensible a mayúsculas/minúsculas: se compara el hash de lo que
        # escribió el usuario contra el hash guardado. Se consume (pop) para
        # que sirva una sola vez.

        captcha_hash = session.pop("captcha", None)
        captcha_ingresado = request.form.get("captcha", "").strip()

        if not captcha_hash or not hmac.compare_digest(
            _hash_captcha(captcha_ingresado), captcha_hash
        ):
            flash(
                "El código de verificación es incorrecto. "
                "Escríbelo tal como aparece, respetando mayúsculas y minúsculas.",
                "danger",
            )
            return redirect(url_for("auth.login"))

        correo = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()

        if not correo or not password:
            flash("Correo y contraseña son campos obligatorios.", "danger")
            return redirect(url_for("auth.login"))

        usuario, col = buscar_login(mongo.db, correo)

        if not usuario:
            flash(
                "No encontramos una cuenta con ese correo. "
                "Verifica los datos o contacta a la administración "
                "de tu fraccionamiento.",
                "danger",
            )
            return redirect(url_for("auth.login"))

        bloqueado_hasta = usuario.get("bloqueado_hasta")

        if bloqueado_hasta:
            if datetime.now() < bloqueado_hasta:
                segundos_restantes = int(
                    (bloqueado_hasta - datetime.now()).total_seconds()
                )
                return render_template(
                    "login.html",
                    bloqueo_activo=True,
                    segundos_restantes=segundos_restantes,
                )

        if not check_password_hash(usuario["password"], password):

            intentos = usuario.get("intentos_fallidos", 0) + 1
            update_data = {"intentos_fallidos": intentos}

            if intentos >= 5:
                update_data["bloqueado_hasta"] = datetime.now() + timedelta(minutes=5)
                flash(
                    "Demasiados intentos fallidos. "
                    "Cuenta bloqueada temporalmente por 5 minutos.",
                    "danger",
                )
            else:
                restantes = 5 - intentos
                flash(
                    f"Contraseña incorrecta. "
                    f"Te quedan {restantes} intentos antes del bloqueo.",
                    "warning",
                )

            col.update_one({"_id": usuario["_id"]}, {"$set": update_data})

            return redirect(url_for("auth.login"))

        if usuario.get("estado") != "activo":
            flash(
                "Tu cuenta está inactiva. "
                "Contacta al administrador del fraccionamiento.",
                "danger",
            )
            return redirect(url_for("auth.login"))

        # ===============
        # CREAR SESIÓN
        # ===============

        # Sesión limpia: borra datos de una sesión anterior (otro usuario,
        # otro fraccionamiento, recuperación de contraseña a medias). Así el
        # tiempo real siempre une al usuario a las salas correctas.
        session.clear()

        session.permanent = True  # <-- AGREGADO: habilita PERMANENT_SESSION_LIFETIME

        session["user_id"] = str(usuario["_id"])
        session["nombre"] = usuario["nombre"]
        session["rol"] = usuario["rol"]
        session["correo"] = usuario["correo"]
        session["fraccionamiento"] = usuario.get("fraccionamiento")

        col.update_one(
            {"_id": usuario["_id"]},
            {
                "$set": {
                    "intentos_fallidos": 0,
                    "bloqueado_hasta": None,
                    "ultimo_acceso": datetime.now(),
                    # "conectado" se pone en True cuando el navegador abre el
                    # socket (evento connect en app.py), no aquí — así el
                    # estado refleja una conexión real, no solo el login.
                }
            },
        )

        mongo.db.logs.insert_one(
            {
                "usuario": usuario["nombre"],
                "correo": usuario["correo"],
                "rol": usuario["rol"],
                "accion": "Inicio de sesión",
                "fecha": datetime.now(),
            }
        )

        if usuario["rol"] == "guardia":
            mongo.db.turnos.insert_one(
                {
                    "guardia": usuario["nombre"],
                    "entrada": datetime.now(),
                    "estado": "activo",
                }
            )

        if usuario["rol"] == "residente" and usuario.get(
            "debe_cambiar_password", False
        ):
            return redirect(url_for("auth.cambiar_password"))

        if usuario["rol"] == "admin":
            return redirect(url_for("admin.dashboard"))

        if usuario["rol"] == "guardia":
            return redirect(url_for("guard.scan_entrada"))

        return redirect(url_for("resident.dashboard"))

    return render_template("login.html", correo_prefill=request.args.get("correo", ""))


# =====================================
# RECUPERAR CONTRASEÑA
# =====================================


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Genera un código temporal de recuperación de contraseña para residentes."""

    es_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method == "GET":

        mostrar_token = session.get("recovery_token_pending_display", False)
        token_generado = session.get("recovery_token") if mostrar_token else None
        expira_raw = session.get("recovery_token_expira")
        if isinstance(expira_raw, str):
            expira = datetime.fromisoformat(expira_raw)
        else:
            expira = expira_raw  # ya es datetime (cookies previas) o None
        if expira and expira.tzinfo is not None:
            expira = expira.replace(tzinfo=None)

        # Si el token ya expiró, no lo mostramos y limpiamos la sesión
        if token_generado and expira and datetime.now() > expira:
            token_generado = None
            session.pop("recovery_token", None)
            session.pop("recovery_token_expira", None)
            session.pop("correo_recuperacion", None)

        # El token se muestra una sola vez: al recargar esta página de nuevo
        # (por ejemplo con el botón "atrás" del navegador) ya no aparecerá,
        # y el usuario verá el formulario para pedir el correo otra vez.
        session["recovery_token_pending_display"] = False

        expira_ms = (
            int(expira.timestamp() * 1000) if (token_generado and expira) else None
        )

        return render_template(
            "recuperar_contrasena.html",
            token_generado=token_generado,
            token_expira_ms=expira_ms,
        )

    # ---- POST: generar el token ----

    correo = request.form["correo"].strip()

    usuario, col = buscar_login(mongo.db, correo)

    if not usuario:
        mensaje = "No hay ninguna cuenta asociada a ese correo electrónico."
        if es_ajax:
            return jsonify(success=False, message=mensaje), 400
        flash(mensaje, "danger")
        return redirect(url_for("auth.forgot_password"))

    if usuario.get("rol") != "residente":
        mensaje = (
            "La recuperación de contraseña es solo para residentes. "
            "Si eres guardia o administrador, contacta al administrador del sistema."
        )
        if es_ajax:
            return jsonify(success=False, message=mensaje), 400
        flash(mensaje, "danger")
        return redirect(url_for("auth.forgot_password"))

    token = str(random.randint(100000, 999999))
    expiracion = datetime.now() + timedelta(minutes=5)

    session["recovery_token"] = token
    session["recovery_token_expira"] = expiracion.isoformat()
    session["correo_recuperacion"] = correo
    # Si es AJAX no habrá otro GET después de esto (no navegamos a ninguna
    # parte), así que no necesitamos la bandera de "mostrar una vez".
    session["recovery_token_pending_display"] = not es_ajax

    col.update_one(
        {"_id": usuario["_id"]},
        {"$set": {"token_recuperacion": token, "token_expira": expiracion}},
    )

    if es_ajax:
        # Respondemos con JSON: el frontend actualiza el DOM sin navegar,
        # por lo que el navegador NUNCA agrega una entrada nueva al
        # historial, sin importar cuántas veces se reenvíe el formulario.
        return jsonify(
            success=True,
            token=token,
            expira_ms=int(expiracion.timestamp() * 1000),
        )

    flash(
        "Código temporal generado. Ingrésalo a continuación para continuar.", "success"
    )

    # PRG (respaldo si el JS está desactivado): nunca renderizar directamente
    # sobre un POST, siempre redirigir. Esto evita el error "Confirmar
    # reenvío del formulario" / ERR_CACHE_MISS al usar el botón de
    # atrás/adelante del navegador.
    return redirect(url_for("auth.forgot_password"))


# =====================================
# VALIDAR TOKEN TEMPORAL
# =====================================


@auth_bp.route("/verify-token", methods=["POST"])
def verify_token():
    """Verifica el código temporal y permite continuar al cambio de contraseña."""

    token_ingresado = request.form["token"].strip()
    token_guardado = session.get("recovery_token")
    expira_raw = session.get("recovery_token_expira")
    if isinstance(expira_raw, str):
        expira = datetime.fromisoformat(expira_raw)
    else:
        expira = expira_raw  # ya es datetime (cookies previas) o None
    if expira and expira.tzinfo is not None:
        expira = expira.replace(tzinfo=None)

    # Validar expiración en backend (el timer del frontend es solo visual)
    if expira and datetime.now() > expira:
        flash("El código ha expirado. Solicita uno nuevo e intenta de nuevo.", "danger")
        session.pop("recovery_token", None)
        session.pop("recovery_token_expira", None)
        return redirect(url_for("auth.forgot_password"))

    if token_guardado and token_ingresado == token_guardado:
        # El token ya cumplió su propósito, lo invalidamos para que no
        # pueda reutilizarse si el usuario vuelve a /forgot-password.
        session.pop("recovery_token", None)
        session.pop("recovery_token_expira", None)
        session.pop("recovery_token_pending_display", None)
        return redirect(url_for("auth.reset_password"))

    flash(
        "El código ingresado no es válido. Solicita uno nuevo e intenta de nuevo.",
        "danger",
    )

    return redirect(url_for("auth.forgot_password"))


# =====================================
# NUEVA CONTRASEÑA
# =====================================


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Establece una nueva contraseña tras validar la sesión de recuperación."""

    correo = session.get("correo_recuperacion")

    if not correo:
        flash(
            "La sesión de recuperación expiró. Inicia el proceso nuevamente.", "danger"
        )
        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template("nueva_contrasena.html", modo="recuperacion")

    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    # Misma regla mínima que en "cambiar contraseña" (el navegador también
    # la valida, pero el servidor no debe depender solo del navegador).
    if len(password) < 8:
        flash("La contraseña debe tener al menos 8 caracteres.", "danger")
        return redirect(url_for("auth.reset_password"))

    if password != confirm_password:
        flash(
            "Las contraseñas no coinciden. Por favor, verifica e intenta de nuevo.",
            "danger",
        )
        return redirect(url_for("auth.reset_password"))

    usuario, col = buscar_login(mongo.db, correo)

    if not usuario:
        flash("La cuenta ya no existe. Contacta a la administración.", "danger")
        return redirect(url_for("auth.login"))

    col.update_one(
        {"_id": usuario["_id"]},
        {
            "$set": {
                "password": generate_password_hash(password),
                "token_recuperacion": None,
                "token_expira": None,
            }
        },
    )

    session.pop("recovery_token", None)
    session.pop("recovery_token_expira", None)
    session.pop("recovery_token_pending_display", None)
    session.pop("correo_recuperacion", None)

    flash(
        "¡Contraseña actualizada con éxito! "
        "Ya puedes iniciar sesión con tu nueva contraseña.",
        "success",
    )

    return redirect(url_for("auth.login"))


@auth_bp.route("/cambiar-password", methods=["GET", "POST"])
def cambiar_password():
    """Permite a un usuario autenticado cambiar su contraseña."""

    if "user_id" not in session:
        return redirect(url_for("auth.login"))

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("La contraseña debe tener al menos 8 caracteres.", "danger")
            return redirect(url_for("auth.cambiar_password"))

        if password != confirm:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect(url_for("auth.cambiar_password"))

        usuario, col = buscar_login(mongo.db, session.get("correo"))
        if not usuario:
            session.clear()
            return redirect(url_for("auth.login"))

        col.update_one(
            {"_id": usuario["_id"]},
            {
                "$set": {
                    "password": generate_password_hash(password),
                    "debe_cambiar_password": False,
                }
            },
        )

        flash("Contraseña actualizada correctamente.", "success")

        rol = session.get("rol")
        if rol == "admin":
            return redirect(url_for("admin.dashboard"))
        if rol == "guardia":
            return redirect(url_for("guard.scan_entrada"))
        return redirect(url_for("resident.dashboard"))

    return render_template("nueva_contrasena.html", modo="cambio_obligatorio")


# ============
# LOGOUT
# ============


@auth_bp.route("/logout")
def logout():
    """Cierra la sesión, finaliza el turno del guardia si aplica y registra el log."""

    user_id = session.get("user_id")
    rol = session.get("rol")

    # Marcamos "conectado" en False de inmediato, sin esperar a que el
    # socket se desconecte solo (eso puede tardar unos segundos). Es el
    # mismo campo que actualiza app.py en el evento "disconnect" de
    # Socket.IO — aquí lo hacemos explícito porque el logout es una acción
    # intencional del usuario y no debería tener ningún retraso visual.
    if user_id:
        try:
            if rol == "residente" and session.get("fraccionamiento"):
                col_usuario = coleccion_residentes(
                    mongo.db, session.get("fraccionamiento")
                )
            else:
                col_usuario = mongo.db.users

            col_usuario.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"conectado": False, "ultima_desconexion": datetime.now()}},
            )
        except Exception:  # pylint: disable=broad-except
            pass

    if rol == "guardia":
        mongo.db.turnos.update_many(
            {
                "guardia": session.get("nombre"),
                "estado": "activo",
            },
            {
                "$set": {
                    "estado": "finalizado",
                    "salida": datetime.now(),
                }
            },
        )

    mongo.db.logs.insert_one(
        {
            "usuario": session.get("nombre"),
            "rol": rol,
            "accion": "Cierre de sesión",
            "fecha": datetime.now(),
        }
    )

    session.clear()

    flash("Sesión cerrada correctamente. ¡Hasta pronto!", "success")

    return redirect(url_for("auth.login"))
