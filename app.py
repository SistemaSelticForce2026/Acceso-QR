import os
import time

os.environ["TZ"] = "America/Mexico_City"
if hasattr(time, "tzset"):
    time.tzset()

from routes.api.auth_api import auth_api
from routes.api.admin_api import admin_api
from routes.api.residente_api import residente_api
from routes.api.guardia_api import guardia_api
from routes.api.qr_api import qr_api
from routes.api.reportes_api import reportes_api
from routes.api.upload_api import upload_api


from flask import Flask, render_template, session, request
from config import Config
from extensions import mongo, socketio

from datetime import datetime

from flask_socketio import join_room

# ======================
# FILTRO HORA AM / PM
# ======================


def hora_ampm(valor):

    if not valor:

        return ""

    formatos = ["%H:%M:%S", "%H:%M"]

    for formato in formatos:

        try:

            hora = datetime.strptime(valor, formato)

            return hora.strftime("%I:%M %p")

        except:

            pass

    return valor


# ===============================
# ÍNDICES DE BASE DE DATOS
# ===============================
def crear_indices():
    """Crea los índices una sola vez al arrancar.

    create_index es idempotente cuando las opciones coinciden, pero lanza
    OperationFailure si ya existe un índice con el mismo nombre y opciones
    distintas (p. ej. 'qr_token' ya creado como ÚNICO en Atlas). En ese caso
    el índice equivalente ya existe, así que ignoramos el conflicto y dejamos
    arrancar la app en vez de abortar."""

    def _idx(coll, *args, **kwargs):
        try:
            coll.create_index(*args, **kwargs)
        except Exception as e:
            print(
                f"AVISO: índice {args} en '{coll.name}' ya existe o no se pudo crear: {e}"
            )

    # --- Índices de rendimiento ---
    _idx(mongo.db.users, "rol")
    _idx(mongo.db.visits, "qr_token", unique=True)
    _idx(mongo.db.visits, "residente_id")
    _idx(mongo.db.visits, "estado")
    _idx(mongo.db.visits, "created_at")
    _idx(mongo.db.visits, "fecha_visita")
    _idx(mongo.db.access_logs, "fecha_hora")
    _idx(mongo.db.incidencias, "fecha_hora")
    _idx(mongo.db.reportes, "fecha")

    # --- Índice único de correo (puede fallar si ya hay correos duplicados) ---
    try:
        mongo.db.users.create_index("correo", unique=True)
    except Exception as e:
        print("AVISO: no se pudo crear índice único en 'correo':", e)
        print("       Revisa si ya tienes correos repetidos en la base.")


# ===============================
# SALAS POR ROL / USUARIO
# ===============================
@socketio.on("connect")
def on_connect():
    rol = session.get("rol")
    user_id = session.get("user_id")
    if rol:
        join_room(f"rol:{rol}")
    if user_id:
        join_room(f"user:{user_id}")


# ================
# CREAR APP
# ================
def create_app():

    app = Flask(__name__, static_folder="static", template_folder="templates")

    app.config.from_object(Config)

    # =====================================
    # MODO MANTENIMIENTO
    # =====================================

    # False = Sistema normal
    # Todos pueden ingresar:
    # Admin, Guardias y Residentes

    # True = Sistema en mantenimiento
    # Solo los administradores pueden ingresar
    # Guardias y Residentes verán la página
    # mantenimiento.html

    MODO_MANTENIMIENTO = True

    @app.before_request
    def mantenimiento():

        if not MODO_MANTENIMIENTO:
            return None

        if request.endpoint in ["auth.login", "auth.logout", "static"]:
            return None

        if session.get("rol") == "admin":
            return None

        return render_template("mantenimiento.html"), 503

    # =====================================
    # CONFIGURAR UPLOADS
    # =====================================

    app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER

    mongo.init_app(app)

    # Crear índices una sola vez al arrancar
    with app.app_context():
        crear_indices()

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        logger=False,
        engineio_logger=False,
    )

    # ===========================
    # REGISTRAR FILTRO JINJA
    # ===========================

    app.add_template_filter(hora_ampm, "hora_ampm")

    # ===========================
    # BLUEPRINTS
    # ===========================

    from routes.auth_routes import auth_bp
    from routes.residente_routes import resident_bp
    from routes.guardia_routes import guard_bp
    from routes.admin_routes import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(resident_bp)
    app.register_blueprint(guard_bp)
    app.register_blueprint(admin_bp)

    # ===========================
    # APIS
    # ===========================

    app.register_blueprint(auth_api)

    app.register_blueprint(admin_api)

    app.register_blueprint(residente_api)

    app.register_blueprint(guardia_api)

    app.register_blueprint(qr_api)

    app.register_blueprint(reportes_api)

    app.register_blueprint(upload_api)

    return app


app = create_app()


# ===============================
# INICIAR APP
# ===============================
if __name__ == "__main__":
    socketio.run(app, debug=False, allow_unsafe_werkzeug=True)
