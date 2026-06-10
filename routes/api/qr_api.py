from flask import Blueprint, jsonify
from extensions import mongo

qr_api = Blueprint("qr_api", __name__)


@qr_api.route("/api/qr/<token>")
def obtener_qr(token):

    visita = mongo.db.visits.find_one({"qr_token": token})

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
