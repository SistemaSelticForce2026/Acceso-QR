"""Acceso a la base de datos: helper para obtener la instancia de MongoDB."""

from extensions import mongo


def get_db():
    """Devuelve la instancia activa de la base de datos MongoDB."""
    return mongo.db
