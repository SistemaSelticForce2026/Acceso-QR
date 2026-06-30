"""Aplicación principal Flask: configuración, filtros, índices y blueprints."""

import os
import time
from datetime import datetime

from flask import Flask, render_template, session, request
from flask_socketio import join_room

from config import Config
from extensions import mongo, socketio
from utils.fraccionamientos import visitas_colecciones

from routes.api.auth_api import auth_api
from routes.api.admin_api import admin_api
from routes.api.residente_api import residente_api
from routes.api.guardia_api import guardia_api
from routes.api.qr_api import qr_api
from routes.api.reportes_api import reportes_api
from routes.api.upload_api import upload_api

os.environ["TZ"] = "America/Mexico_City"
if hasattr(time, "tzset"):
    time.tzset()


# ======================
# FILTRO HORA AM / PM
# ======================


def hora_ampm(valor):
    """Convierte una cadena HH:MM o HH:MM:SS al formato 12 h con AM/PM."""
    if not valor:
        return ""
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(valor, formato).strftime("%I:%M %p")
        except ValueError:
            pass
    return valor


# ===============================
# ÍNDICES DE BASE DE DATOS
# ===============================


def crear_indices():
    """Crea los índices una sola vez al arrancar.

    create_index es idempotente cuando las opciones coinciden, pero lanza
    OperationFailure si ya existe un índice con el mismo nombre y opciones
    distintas. En ese caso el índice equivalente ya existe, así que ignoramos
    el conflicto y dejamos arrancar la app en vez de abortar.
    """

    def _idx(coll, *args, **kwargs):
        try:
            coll.create_index(*args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            print(
                f"AVISO: índice {args} en '{coll.name}' "
                f"ya existe o no se pudo crear: {exc}"
            )

    _idx(mongo.db.users, "rol")
    _idx(mongo.db.access_logs, "fecha_hora")
    _idx(mongo.db.incidencias, "fecha_hora")
    _idx(mongo.db.reportes, "fecha")

    for col_name in visitas_colecciones(mongo.db).values():
        col = mongo.db[col_name]
        _idx(col, "qr_token", unique=True)
        _idx(col, "residente_id")
        _idx(col, "estado")
        _idx(col, "created_at")
        _idx(col, "fecha_visita")

    try:
        mongo.db.users.create_index("correo", unique=True)
    except Exception as exc:  # pylint: disable=broad-except
        print("AVISO: no se pudo crear índice único en 'correo':", exc)
        print("       Revisa si ya tienes correos repetidos en la base.")


# ===============================
# SALAS POR ROL / USUARIO
# ===============================


@socketio.on("connect")
def on_connect():
    """Une al cliente a las salas de su rol y su usuario al conectarse."""
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
    """Crea y configura la instancia de Flask."""

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # =====================================
    # MODO MANTENIMIENTO
    # False = Sistema normal (todos entran)
    # True  = Solo administradores entran
    # =====================================

    modo_mantenimiento = False

    @app.before_request
    def mantenimiento():
        if not modo_mantenimiento:
            return None
        if request.endpoint in ["auth.login", "auth.logout", "static"]:
            return None
        if session.get("rol") == "admin":
            return None
        return render_template("mantenimiento.html"), 503

    app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER

    mongo.init_app(app)

    with app.app_context():
        crear_indices()

    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        logger=False,
        engineio_logger=False,
    )

    app.add_template_filter(hora_ampm, "hora_ampm")

    # ===========================
    # BLUEPRINTS
    # ===========================

    from routes.auth_routes import auth_bp  # noqa: PLC0415
    from routes.residente_routes import resident_bp  # noqa: PLC0415
    from routes.guardia_routes import guard_bp  # noqa: PLC0415
    from routes.admin_routes import admin_bp  # noqa: PLC0415

    app.register_blueprint(auth_bp)
    app.register_blueprint(resident_bp)
    app.register_blueprint(guard_bp)
    app.register_blueprint(admin_bp)

    app.register_blueprint(auth_api)
    app.register_blueprint(admin_api)
    app.register_blueprint(residente_api)
    app.register_blueprint(guardia_api)
    app.register_blueprint(qr_api)
    app.register_blueprint(reportes_api)
    app.register_blueprint(upload_api)

    return app


app = create_app()  # pylint: disable=invalid-name

# ===============================
# INICIAR APP
# ===============================

if __name__ == "__main__":
    socketio.run(app, debug=False, allow_unsafe_werkzeug=True)
