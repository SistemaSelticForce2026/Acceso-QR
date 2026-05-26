from app import create_app

from extensions import mongo

from werkzeug.security import generate_password_hash

from datetime import datetime

# =====================================================
# CREAR APP
# =====================================================

app = create_app()

# =====================================================
# CONTEXTO FLASK
# =====================================================

with app.app_context():

    print("\n=====================================")
    print("ACTUALIZANDO USUARIOS DEL SISTEMA")
    print("=====================================\n")

    # =================================================
    # =================================================
    # ADMINISTRADOR
    # =================================================
    # =================================================

    # =================================================
    # CORREO ACTUAL DEL ADMIN EN MONGODB
    # ESTE CORREO DEBE EXISTIR YA EN LA BASE
    # =================================================

    correo_actual_admin = "adminSelticForce@gmail.com"

    # =================================================
    # NUEVO CORREO ADMIN
    # AQUI PUEDES CAMBIARLO MANUALMENTE
    # =================================================

    nuevo_correo_admin = "adminSeltic@gmail.com"

    # =================================================
    # NUEVA CONTRASEÑA ADMIN
    # AQUI PUEDES CAMBIARLA MANUALMENTE
    # =================================================

    nueva_password_admin = "Admin321*"

    # =================================================
    # BUSCAR ADMIN
    # =================================================

    admin_existente = mongo.db.users.find_one(
        {
            "correo": correo_actual_admin,
            "rol": "admin",
        }
    )

    # =================================================
    # SI EXISTE -> ACTUALIZAR
    # =================================================

    if admin_existente:

        mongo.db.users.update_one(
            {"_id": admin_existente["_id"]},
            {
                "$set": {
                    # =============================
                    # NUEVO CORREO
                    # =============================
                    "correo": nuevo_correo_admin,
                    # =============================
                    # NUEVA CONTRASEÑA
                    # =============================
                    "password": generate_password_hash(nueva_password_admin),
                    # =============================
                    # ESTADO
                    # =============================
                    "estado": "activo",
                    # =============================
                    # FECHA ACTUALIZACIÓN
                    # =============================
                    "updated_at": datetime.now(),
                }
            },
        )

        print("ADMINISTRADOR ACTUALIZADO\n")

        print(f"ID: {admin_existente['_id']}")

        print(f"Nuevo correo: {nuevo_correo_admin}")

    else:

        print("NO EXISTE UN ADMIN CON ESE CORREO\n")

    # =================================================
    # =================================================
    # GUARDIA
    # =================================================
    # =================================================

    # =================================================
    # CORREO ACTUAL DEL GUARDIA EN MONGODB
    # ESTE CORREO DEBE EXISTIR YA EN LA BASE
    # =================================================

    correo_actual_guardia = "guardiaSelticForce@gmail.com"

    # =================================================
    # NUEVO CORREO GUARDIA
    # AQUI PUEDES CAMBIARLO MANUALMENTE
    # =================================================

    nuevo_correo_guardia = "guardiaSeltic@gmail.com"

    # =================================================
    # NUEVA CONTRASEÑA GUARDIA
    # AQUI PUEDES CAMBIARLA MANUALMENTE
    # =================================================

    nueva_password_guardia = "Guardia321*"

    # =================================================
    # BUSCAR GUARDIA
    # =================================================

    guardia_existente = mongo.db.users.find_one(
        {
            "correo": correo_actual_guardia,
            "rol": "guardia",
        }
    )

    # =================================================
    # SI EXISTE -> ACTUALIZAR
    # =================================================

    if guardia_existente:

        mongo.db.users.update_one(
            {"_id": guardia_existente["_id"]},
            {
                "$set": {
                    # =============================
                    # NUEVO CORREO
                    # =============================
                    "correo": nuevo_correo_guardia,
                    # =============================
                    # NUEVA CONTRASEÑA
                    # =============================
                    "password": generate_password_hash(nueva_password_guardia),
                    # =============================
                    # ESTADO
                    # =============================
                    "estado": "activo",
                    # =============================
                    # FECHA ACTUALIZACIÓN
                    # =============================
                    "updated_at": datetime.now(),
                }
            },
        )

        print("GUARDIA ACTUALIZADO\n")

        print(f"ID: {guardia_existente['_id']}")

        print(f"Nuevo correo: {nuevo_correo_guardia}")

    else:

        print("NO EXISTE UN GUARDIA CON ESE CORREO\n")

    # =================================================
    # MENSAJES FINALES
    # =================================================

    print("\n=====================================")
    print("CREDENCIALES ACTUALIZADAS")
    print("=====================================\n")

    print("ADMIN")

    print(f"Correo: {nuevo_correo_admin}")

    print(f"Contraseña: {nueva_password_admin}\n")

    print("GUARDIA")

    print(f"Correo: {nuevo_correo_guardia}")

    print(f"Contraseña: {nueva_password_guardia}\n")

    print("=====================================")
    print("PROCESO FINALIZADO")
    print("=====================================\n")
