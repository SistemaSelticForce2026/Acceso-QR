def user_schema(nombre, email, password, rol, residencia=None):
    return {
        "nombre": nombre,
        "email": email,
        "password": password,
        "rol": rol,
        "residencia": residencia,
        "estado": "activo",
    }
