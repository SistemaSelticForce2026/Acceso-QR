# utils/qr_generator.py
import io
import qrcode
import cloudinary.uploader
import utils.cloudinary_config  # noqa: F401
from utils.fraccionamientos import _slug_fraccionamiento


def generate_qr(token, fraccionamiento):
    """Genera un QR y lo sube a accesoqr/{fraccionamiento}/qr."""
    img = qrcode.make(token)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    slug = _slug_fraccionamiento(fraccionamiento)
    folder = f"accesoqr/{slug}/qr"

    resultado = cloudinary.uploader.upload(
        buffer,
        folder=folder,
        public_id=token,
        overwrite=True,
    )

    return resultado["secure_url"]
