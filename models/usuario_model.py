"""Modelo de usuario: estructura del documento de usuario en MongoDB."""


def user_schema(nombre, email, password, rol, residencia=None):
    """Construye el documento de un usuario con estado activo por defecto."""
    return {
        "nombre": nombre,
        "email": email,
        "password": password,
        "rol": rol,
        "residencia": residencia,
        "estado": "activo",
    }
