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

        correo = request.form["correo"].strip().lower()

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

            flash("Las contraseñas no coinciden.", "danger")

            return redirect(url_for("auth.register"))

        # ===============================
        # VALIDAR CORREO DUPLICADO
        # ==============================

        correo_existente = mongo.db.users.find_one({"correo": correo})

        if correo_existente:

            flash("El correo electrónico ya se encuentra registrado.", "danger")

            return redirect(url_for("auth.register"))

        # =============================
        # VALIDAR CASA DUPLICADA
        # =============================

        casa_existente = mongo.db.users.find_one(
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
                f"La casa {numero_casa} ya se encuentra registrada en "
                f"{privada.title()} - {fraccionamiento.title()}",
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

        mongo.db.users.insert_one(usuario)

        # ====================
        # REFRESH SOCKET
        # ====================

        socketio.emit("refresh")

        # ====================
        # MENSAJE
        # ====================

        flash("Cuenta creada correctamente.", "success")

        return redirect(url_for("auth.login"))

    return render_template("registro.html")


# ============
# LOGIN
# ============


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        correo = request.form["correo"].strip().lower()

        password = request.form["password"]

        # =================
        # BUSCAR USUARIO
        # =================

        usuario = mongo.db.users.find_one({"correo": correo})

        # ===================
        # USUARIO NO EXISTE
        # ===================

        if not usuario:

            flash("El usuario no existe.", "danger")

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
                    "Demasiados intentos fallidos. " "Cuenta bloqueada temporalmente.",
                    "danger",
                )

            else:

                restantes = 5 - intentos

                flash(
                    f"Contraseña incorrecta. " f"Intentos restantes: {restantes}",
                    "warning",
                )

            mongo.db.users.update_one({"_id": usuario["_id"]}, {"$set": update_data})

            return redirect(url_for("auth.login"))

        # ================
        # VALIDAR ESTADO
        # ================

        if usuario.get("estado") != "activo":

            flash("Tu cuenta se encuentra inactiva.", "danger")

            return redirect(url_for("auth.login"))

        # ===============
        # CREAR SESIÓN
        # ===============

        session["user_id"] = str(usuario["_id"])

        session["nombre"] = usuario["nombre"]

        session["rol"] = usuario["rol"]

        session["correo"] = usuario["correo"]

        # =====================
        # RESETEAR INTENTOS
        # =====================

        mongo.db.users.update_one(
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
        # SOCKET REFRESH
        # ===================

        socketio.emit("refresh")

        # ===================
        # REDIRECCIONES
        # ===================

        if usuario["rol"] == "admin":

            return redirect(url_for("admin.dashboard"))

        elif usuario["rol"] == "guardia":

            return redirect(url_for("guard.dashboard"))

        else:

            return redirect(url_for("resident.dashboard"))

    return render_template("login.html")


# ============
# LOGOUT
# ============


@auth_bp.route("/logout")
def logout():

    # ===========================
    # FINALIZAR TURNOS GUARDIAS
    # ============================

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

    # ===============
    # LOGS
    # ===============

    mongo.db.logs.insert_one(
        {
            "usuario": session.get("nombre"),
            "rol": session.get("rol"),
            "accion": "Cierre de sesión",
            "fecha": datetime.now(),
        }
    )

    # ======================
    # LIMPIAR SESIÓN
    # ======================

    session.clear()

    socketio.emit("refresh")

    flash("Sesión cerrada correctamente.", "success")

    return redirect(url_for("auth.login"))
