"""Rutas de autenticación: registro, login, recuperación de contraseña y logout."""

import random
from datetime import datetime, timedelta

from bson import ObjectId
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import mongo
from utils.fraccionamientos import (
    buscar_login,
    coleccion_residentes,
    correo_ya_existe,
    es_fraccionamiento_valido,
    obtener_fraccionamientos,
)

# ==================
# BLUEPRINT AUTH
# ==================

auth_bp = Blueprint("auth", __name__)

# ================
# INICIO
# ================


@auth_bp.route("/")
def index():
    """Redirige la raíz del sitio a la pantalla de login."""

    return redirect(url_for("auth.login"))


# =======================
# REGISTRO RESIDENTE
# =======================


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registra un nuevo residente validando correo, casa y fraccionamiento."""

    if request.method == "POST":

        nombre = request.form["nombre"].strip()
        correo = request.form["correo"].strip()
        telefono = request.form["telefono"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        fraccionamiento = request.form["fraccionamiento"].strip().lower()
        privada = request.form["privada"].strip().lower()
        numero_casa = str(request.form["numero_casa"]).strip()

        if password != confirm_password:
            flash(
                "Las contraseñas no coinciden. Por favor, verifica e intenta de nuevo.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        if not es_fraccionamiento_valido(mongo.db, fraccionamiento):
            flash("Selecciona un fraccionamiento válido.", "danger")
            return redirect(url_for("auth.register"))

        residentes_col = coleccion_residentes(mongo.db, fraccionamiento)

        if correo_ya_existe(mongo.db, correo):
            flash(
                "Este correo electrónico ya está registrado. ¿Olvidaste tu contraseña?",
                "danger",
            )
            return redirect(url_for("auth.register"))

        casa_existente = residentes_col.find_one(
            {
                "rol": "residente",
                "fraccionamiento": fraccionamiento,
                "privada": privada,
                "numero_casa": str(numero_casa),
            }
        )

        if casa_existente:
            flash(
                f"La casa {numero_casa} ya está registrada en "
                f"{privada.title()} – {fraccionamiento.title()}.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        usuario = {
            "nombre": nombre,
            "correo": correo,
            "password": generate_password_hash(password),
            "rol": "residente",
            "fraccionamiento": fraccionamiento,
            "privada": privada,
            "numero_casa": str(numero_casa),
            "telefono": telefono,
            "estado": "activo",
            "created_at": datetime.now(),
            "ultimo_acceso": None,
            "intentos_fallidos": 0,
            "bloqueado_hasta": None,
            "conectado": False,
        }

        residentes_col.insert_one(usuario)

        flash("¡Cuenta creada con éxito! Ya puedes iniciar sesión.", "success")

        return redirect(url_for("auth.login", correo=correo))

    return render_template(
        "registro.html", fraccionamientos=obtener_fraccionamientos(mongo.db)
    )


# ============
# LOGIN
# ============


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Autentica al usuario, gestiona bloqueos por intentos y crea la sesión."""

    if request.method == "POST":

        correo = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()

        if not correo or not password:
            flash("Correo y contraseña son campos obligatorios.", "danger")
            return redirect(url_for("auth.login"))

        usuario, col = buscar_login(mongo.db, correo)

        if not usuario:
            flash(
                "No encontramos una cuenta con ese correo. "
                "Verifica los datos o regístrate.",
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
        return render_template("nueva_contrasena.html")

    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    if password != confirm_password:
        flash(
            "Las contraseñas no coinciden. Por favor, verifica e intenta de nuevo.",
            "danger",
        )
        return redirect(url_for("auth.reset_password"))

    usuario, col = buscar_login(mongo.db, correo)

    if not usuario:
        flash("La cuenta ya no existe. Regístrate de nuevo.", "danger")
        return redirect(url_for("auth.register"))

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

    return render_template("cambiar_password.html")


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
