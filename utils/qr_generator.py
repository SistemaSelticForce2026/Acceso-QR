import qrcode
import os


def generate_qr(token):
    folder = "static/qr"
    os.makedirs(folder, exist_ok=True)

    filename = f"{token}.png"
    path = os.path.join(folder, filename)

    img = qrcode.make(token)
    img.save(path)

    return f"/static/qr/{filename}"
