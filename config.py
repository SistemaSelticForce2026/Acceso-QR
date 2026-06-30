"""Configuración central de la aplicación Flask."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Parámetros de configuración cargados desde variables de entorno."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    MONGO_URI = os.getenv("MONGO_URI")
    UPLOAD_FOLDER = os.path.join("static", "uploads")
