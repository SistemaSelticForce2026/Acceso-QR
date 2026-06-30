"""Endpoints de la API de reportes."""

from flask import Blueprint, jsonify

from extensions import mongo
from utils.fraccionamientos import contar_visitas

reportes_api = Blueprint("reportes_api", __name__)


@reportes_api.route("/api/reportes")
def reportes():
    """Devuelve el total de visitas, accesos e incidencias registradas."""
    return jsonify(
        {
            "visitas": contar_visitas(mongo.db),
            "accesos": mongo.db.access_logs.count_documents({}),
            "incidencias": mongo.db.incidencias.count_documents({}),
        }
    )
