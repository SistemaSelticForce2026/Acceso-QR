import io
import qrcode
import cloudinary.uploader

from utils.cloudinary_config import *

# =========================================
# GENERAR QR
# =========================================


def generate_qr(token):

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
