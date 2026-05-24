import os
import uuid

from flask import current_app

from werkzeug.utils import secure_filename

# =========================================
# GUARDAR IMAGEN
# =========================================


def guardar_imagen(archivo, subcarpeta):

    if not archivo or not archivo.filename:

        return None

    # =====================================
    # NOMBRE ÚNICO
    # =====================================

    nombre = f"{uuid.uuid4().hex}_{secure_filename(archivo.filename)}"

    # =====================================
    # CARPETA DESTINO
    # =====================================

    carpeta = os.path.join(current_app.root_path, "static", "uploads", subcarpeta)

    os.makedirs(carpeta, exist_ok=True)

    # =====================================
    # RUTA COMPLETA
    # =====================================

    ruta = os.path.join(carpeta, nombre)

    # =====================================
    # GUARDAR ARCHIVO
    # =====================================

    archivo.save(ruta)

    # =====================================
    # RETORNAR URL
    # =====================================

    return f"/static/uploads/{subcarpeta}/{nombre}"
