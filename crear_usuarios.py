from app import create_app
from extensions import mongo
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():

    mongo.db.users.delete_many(
        {"correo": {"$in": ["admin@gmail.com", "guardia@gmail.com"]}}
    )

    admin = {
        "nombre": "Administrador",
        "correo": "admin@gmail.com",
        "password": generate_password_hash("123456"),
        "rol": "admin",
        "estado": "activo",
    }

    guardia = {
        "nombre": "Guardia Principal",
        "correo": "guardia@gmail.com",
        "password": generate_password_hash("123456"),
        "rol": "guardia",
        "telefono": "7220000000",
        "turno": "nocturno",
        "estado": "activo",
    }

    mongo.db.users.insert_one(admin)
    mongo.db.users.insert_one(guardia)

    print("Admin y guardia creados correctamente")
