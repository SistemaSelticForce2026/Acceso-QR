"""Configuración central de la aplicación Flask."""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Parámetros de configuración cargados desde variables de entorno."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    MONGO_URI = os.getenv("MONGO_URI")
    UPLOAD_FOLDER = os.path.join("static", "uploads")

    # =====================================
    # DURACIÓN MÁXIMA DE LA SESIÓN (cookie)
    # Debe ser un poco mayor a TIEMPO_INACTIVIDAD
    # de app.py, para que sea la inactividad
    # (no la cookie) la que cierre la sesión.
    # =====================================
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=10)
