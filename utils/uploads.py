"""Utilidades para subir imágenes a Cloudinary."""

import cloudinary.uploader
import utils.cloudinary_config  # noqa: F401


def guardar_imagen(archivo, subcarpeta):
    """Sube un archivo de imagen a Cloudinary y retorna url y public_id."""
    if not archivo or not archivo.filename:
        return None

    resultado = cloudinary.uploader.upload(archivo, folder=f"accesoqr/{subcarpeta}")

    return {"url": resultado["secure_url"], "public_id": resultado["public_id"]}
