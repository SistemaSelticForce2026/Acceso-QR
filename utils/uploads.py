# utils/uploads.py
import cloudinary.uploader
import utils.cloudinary_config  # noqa: F401
from utils.fraccionamientos import _slug_fraccionamiento


def guardar_imagen(archivo, fraccionamiento, tipo):
    """Sube un archivo de imagen a Cloudinary bajo accesoqr/{fraccionamiento}/{tipo}."""
    if not archivo or not archivo.filename:
        return None

    slug = _slug_fraccionamiento(fraccionamiento)
    folder = f"accesoqr/{slug}/{tipo}"

    resultado = cloudinary.uploader.upload(archivo, folder=folder)

    return {"url": resultado["secure_url"], "public_id": resultado["public_id"]}
