"""Script para crear o restablecer el usuario administrador."""

from datetime import datetime
from werkzeug.security import generate_password_hash
from app import create_app
from extensions import mongo

app = create_app()

with app.app_context():

    # ============================================
    # CREDENCIALES DEL ADMINISTRADOR
    # Cambia estos valores si lo necesitas
    # ============================================
    CORREO_ADMIN = "adminSeltic@gmail.com"
    PASSWORD_ADMIN = "Admin321*"
    NOMBRE_ADMIN = "Administrador"

    print("\n=====================================")
    print("CONFIGURACIÓN DE ADMINISTRADOR")
    print("=====================================\n")

    admin = mongo.db.users.find_one({"correo": CORREO_ADMIN, "rol": "admin"})

    if admin:
        mongo.db.users.update_one(
            {"_id": admin["_id"]},
            {
                "$set": {
                    "password": generate_password_hash(PASSWORD_ADMIN),
                    "estado": "activo",
                    "updated_at": datetime.now(),
                }
            },
        )
        print("ADMINISTRADOR ACTUALIZADO (contraseña restablecida)")
    else:
        mongo.db.users.insert_one(
            {
                "nombre": NOMBRE_ADMIN,
                "correo": CORREO_ADMIN,
                "password": generate_password_hash(PASSWORD_ADMIN),
                "rol": "admin",
                "estado": "activo",
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        )
        print("ADMINISTRADOR CREADO")

    print("\n-------------------------------------")
    print("CREDENCIALES DE ACCESO")
    print("-------------------------------------")
    print(f"Correo:     {CORREO_ADMIN}")
    print(f"Contraseña: {PASSWORD_ADMIN}")
    print("=====================================\n")
