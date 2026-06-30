"""Utilidades para generar y subir códigos QR a Cloudinary."""

import io
import qrcode
import cloudinary.uploader
import utils.cloudinary_config  # noqa: F401


def generate_qr(token):
    """Genera un QR a partir del token y lo sube a Cloudinary."""
    img = qrcode.make(token)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    resultado = cloudinary.uploader.upload(
        buffer,
        folder="accesoqr/qr",
        public_id=token,
        overwrite=True,
    )

    return resultado["secure_url"]
