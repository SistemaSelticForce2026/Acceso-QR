from app import create_app
from extensions import mongo
from werkzeug.security import generate_password_hash
from datetime import datetime

app = create_app()

with app.app_context():

    # ============================================
    # CREDENCIALES DEL ADMINISTRADOR
    # Cambia estos valores si lo necesitas
    # ============================================
    correo_admin = "adminSeltic@gmail.com"
    password_admin = "Admin321*"
    nombre_admin = "Administrador"

    print("\n=====================================")
    print("CONFIGURACIÓN DE ADMINISTRADOR")
    print("=====================================\n")

    admin = mongo.db.users.find_one({"correo": correo_admin, "rol": "admin"})

    if admin:
        # Ya existe -> solo restablece contraseña y lo deja activo
        mongo.db.users.update_one(
            {"_id": admin["_id"]},
            {
                "$set": {
                    "password": generate_password_hash(password_admin),
                    "estado": "activo",
                    "updated_at": datetime.now(),
                }
            },
        )
        print("ADMINISTRADOR ACTUALIZADO (contraseña restablecida)")
    else:
        # No existe -> lo crea
        mongo.db.users.insert_one(
            {
                "nombre": nombre_admin,
                "correo": correo_admin,
                "password": generate_password_hash(password_admin),
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
    print(f"Correo:     {correo_admin}")
    print(f"Contraseña: {password_admin}")
    print("=====================================\n")
