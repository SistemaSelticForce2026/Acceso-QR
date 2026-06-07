import cloudinary.uploader

from utils.cloudinary_config import *

# =========================================
# GUARDAR IMAGEN
# =========================================


def guardar_imagen(archivo, subcarpeta):

    if not archivo or not archivo.filename:

        return None

    resultado = cloudinary.uploader.upload(archivo, folder=f"accesoqr/{subcarpeta}")

    return {"url": resultado["secure_url"], "public_id": resultado["public_id"]}
