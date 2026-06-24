from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from datetime import datetime, timedelta

from extensions import mongo, socketio

from utils.fraccionamientos import (
    es_fraccionamiento_valido,
    coleccion_residentes,
    correo_ya_existe,
    buscar_login,
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

    return redirect(url_for("auth.login"))


# =======================
# REGISTRO RESIDENTE
# =======================


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        # =================
        # OBTENER DATOS
        # ==================

        nombre = request.form["nombre"].strip()

        correo = request.form["correo"].strip()

        telefono = request.form["telefono"].strip()

        password = request.form["password"]

        confirm_password = request.form["confirm_password"]

        fraccionamiento = request.form["fraccionamiento"].strip().lower()

        privada = request.form["privada"].strip().lower()

        # ==============================
        # CONVERTIR SIEMPRE A STRING
        # ============================

        numero_casa = str(request.form["numero_casa"]).strip()

        # =========================
        # VALIDAR CONTRASEÑAS
        # =========================

        if password != confirm_password:

            flash(
                "Las contraseñas no coinciden. Por favor, verifica e intenta de nuevo.",
                "danger",
            )

            return redirect(url_for("auth.register"))

        # =========================================
        # VALIDAR FRACCIONAMIENTO PERMITIDO
        # =========================================

        if not es_fraccionamiento_valido(mongo.db, fraccionamiento):

            flash("Selecciona un fraccionamiento válido.", "danger")

            return redirect(url_for("auth.register"))

        # =========================================
        # COLECCIÓN DESTINO (según fraccionamiento)
        # =========================================

        residentes_col = coleccion_residentes(mongo.db, fraccionamiento)

        # ===============================
        # VALIDAR CORREO DUPLICADO
        # (en users + las 3 colecciones)
        # ==============================

        if correo_ya_existe(mongo.db, correo):

            flash(
                "Este correo electrónico ya está registrado. ¿Olvidaste tu contraseña?",
                "danger",
            )

            return redirect(url_for("auth.register"))

        # =============================
        # VALIDAR CASA DUPLICADA
        # (dentro de SU fraccionamiento)
        # =============================

        casa_existente = residentes_col.find_one(
            {
                "rol": "residente",
                "fraccionamiento": fraccionamiento,
                "privada": privada,
                "numero_casa": str(numero_casa),
            }
        )

        # ===================
        # SI YA EXISTE
        # ===================

        if casa_existente:

            flash(
                f"La casa {numero_casa} ya está registrada en {privada.title()} – {fraccionamiento.title()}.",
                "danger",
            )

            return redirect(url_for("auth.register"))

        # ===================
        # CREAR USUARIO
        # ===================

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
        }

        # ====================
        # INSERTAR USUARIO
        # ====================

        residentes_col.insert_one(usuario)

        # ====================
        # MENSAJE
        # ====================

        flash("¡Cuenta creada con éxito! Ya puedes iniciar sesión.", "success")

        return redirect(url_for("auth.login"))

    return render_template(
        "registro.html", fraccionamientos=obtener_fraccionamientos(mongo.db)
    )


# ============
# LOGIN
# ============


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        correo = request.form.get("correo", "").strip()
        password = request.form.get("password", "").strip()

        if not correo or not password:

            flash("Correo y contraseña son campos obligatorios.", "danger")

            return redirect(url_for("auth.login"))

        # =================
        # BUSCAR USUARIO
        # =================

        usuario, col = buscar_login(mongo.db, correo)

        # ===================
        # USUARIO NO EXISTE
        # ===================

        if not usuario:

            flash(
                "No encontramos una cuenta con ese correo. Verifica los datos o regístrate.",
                "danger",
            )

            return redirect(url_for("auth.login"))

        # ===================
        # BLOQUEO TEMPORAL
        # ===================

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

        # ====================
        # VALIDAR CONTRASEÑA
        # ===================

        if not check_password_hash(usuario["password"], password):

            intentos = usuario.get("intentos_fallidos", 0) + 1

            update_data = {"intentos_fallidos": intentos}

            # ==============================
            # BLOQUEAR SI SUPERA EL LÍMITE
            # ===============================

            if intentos >= 5:

                update_data["bloqueado_hasta"] = datetime.now() + timedelta(minutes=5)

                flash(
                    "Demasiados intentos fallidos. Cuenta bloqueada temporalmente por 5 minutos.",
                    "danger",
                )

            else:

                restantes = 5 - intentos

                flash(
                    f"Contraseña incorrecta. Te quedan {restantes} intentos antes del bloqueo.",
                    "warning",
                )

            col.update_one({"_id": usuario["_id"]}, {"$set": update_data})

            return redirect(url_for("auth.login"))

        # ================
        # VALIDAR ESTADO
        # ================

        if usuario.get("estado") != "activo":

            flash(
                "Tu cuenta está inactiva. Contacta al administrador del fraccionamiento.",
                "danger",
            )

            return redirect(url_for("auth.login"))

        # ===============
        # CREAR SESIÓN
        # ===============

        session["user_id"] = str(usuario["_id"])

        session["nombre"] = usuario["nombre"]

        session["rol"] = usuario["rol"]

        session["correo"] = usuario["correo"]

        session["fraccionamiento"] = usuario.get("fraccionamiento")

        # =====================
        # RESETEAR INTENTOS
        # =====================

        col.update_one(
            {"_id": usuario["_id"]},
            {
                "$set": {
                    "intentos_fallidos": 0,
                    "bloqueado_hasta": None,
                    "ultimo_acceso": datetime.now(),
                }
            },
        )

        # ================
        # LOG SISTEMA
        # ================

        mongo.db.logs.insert_one(
            {
                "usuario": usuario["nombre"],
                "correo": usuario["correo"],
                "rol": usuario["rol"],
                "accion": "Inicio de sesión",
                "fecha": datetime.now(),
            }
        )

        # ===================
        # TURNOS GUARDIAS
        # ===================

        if usuario["rol"] == "guardia":

            mongo.db.turnos.insert_one(
                {
                    "guardia": usuario["nombre"],
                    "entrada": datetime.now(),
                    "estado": "activo",
                }
            )

        # ===================
        # REDIRECCIONES
        # ===================

        if usuario["rol"] == "admin":

            return redirect(url_for("admin.dashboard"))

        elif usuario["rol"] == "guardia":

            return redirect(url_for("guard.scan_entrada"))

        else:

            return redirect(url_for("resident.dashboard"))

    return render_template("login.html")


# =====================================
# RECUPERAR CONTRASEÑA
# =====================================


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "GET":

        return render_template("recuperar_contrasena.html")

    correo = request.form["correo"].strip()

    usuario, col = buscar_login(mongo.db, correo)

    if not usuario:

        flash("No hay ninguna cuenta asociada a ese correo electrónico.", "danger")

        return redirect(url_for("auth.forgot_password"))

    # ============================================
    # SOLO RESIDENTES PUEDEN RECUPERAR POR ESTE MEDIO
    # ============================================
    if usuario.get("rol") != "residente":

        flash(
            "La recuperación de contraseña es solo para residentes. "
            "Si eres guardia o administrador, contacta al administrador del sistema.",
            "danger",
        )

        return redirect(url_for("auth.forgot_password"))

    import random

    token = str(random.randint(100000, 999999))

    expiracion = datetime.now() + timedelta(minutes=5)

    session["recovery_token"] = token

    session["correo_recuperacion"] = correo

    col.update_one(
        {"_id": usuario["_id"]},
        {"$set": {"token_recuperacion": token, "token_expira": expiracion}},
    )

    flash(
        "Código temporal generado. Ingrésalo a continuación para continuar.", "success"
    )

    return render_template("recuperar_contrasena.html", token_generado=token)


# =====================================
# VALIDAR TOKEN TEMPORAL
# =====================================


@auth_bp.route("/verify-token", methods=["POST"])
def verify_token():

    token_ingresado = request.form["token"]

    token_guardado = session.get("recovery_token")

    if token_ingresado == token_guardado:

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

    # Actualizar en la colección correcta
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

    session.pop("correo_recuperacion", None)

    flash(
        "¡Contraseña actualizada con éxito! Ya puedes iniciar sesión con tu nueva contraseña.",
        "success",
    )

    return redirect(url_for("auth.login"))


@auth_bp.route("/cambiar-password", methods=["GET", "POST"])
def cambiar_password():

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
        elif rol == "guardia":
            return redirect(url_for("guard.scan_entrada"))
        else:
            return redirect(url_for("resident.dashboard"))

    return render_template("cambiar_password.html")


# ============
# LOGOUT
# ============


@auth_bp.route("/logout")
def logout():

    if session.get("rol") == "guardia":

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
            "rol": session.get("rol"),
            "accion": "Cierre de sesión",
            "fecha": datetime.now(),
        }
    )

    session.clear()

    flash("Sesión cerrada correctamente. ¡Hasta pronto!", "success")

    return redirect(url_for("auth.login"))
