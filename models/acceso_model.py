"""Modelo de acceso: estructura del registro de validaciones de QR en MongoDB."""


def access_schema(visita_id, guardia_id, accion, resultado):
    """Construye el documento de un registro de acceso (entrada/salida)."""
    return {
        "visita_id": visita_id,
        "guardia_id": guardia_id,
        "accion": accion,
        "resultado": resultado,
    }
