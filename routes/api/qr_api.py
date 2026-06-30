"""Endpoints de API públicos para consultar un QR por token."""

# pylint: disable=missing-function-docstring

from flask import Blueprint, jsonify

from extensions import mongo
from utils.fraccionamientos import visitas_colecciones

qr_api = Blueprint("qr_api", __name__)


@qr_api.route("/api/qr/<token>")
def obtener_qr(token):
    visita = None

    for col_name in visitas_colecciones(mongo.db).values():
        visita = mongo.db[col_name].find_one({"qr_token": token})
        if visita:
            break

    if not visita:
        return jsonify({"success": False, "mensaje": "QR no encontrado"})

    return jsonify(
        {
            "success": True,
            "visitante": visita.get("nombre_visitante"),
            "estado": visita.get("estado"),
            "qr_estado": visita.get("qr_estado"),
        }
    )
