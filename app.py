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

    MODO_MANTENIMIENTO = False

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
