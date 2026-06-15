import os


class Config:

    SECRET_KEY = "access_qr_secret_key"

    MONGO_URI = "mongodb+srv://al222411673_db_user:AccessQR2026@accesoqr.mzgfuac.mongodb.net/accesoqr?retryWrites=true&w=majority&appName=accesoqr"

    UPLOAD_FOLDER = os.path.join("static", "uploads")



