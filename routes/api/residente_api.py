from flask import Blueprint, jsonify
from extensions import mongo

residente_api = Blueprint("residente_api", __name__)


@residente_api.route("/api/residente/visitas")
def obtener_visitas():

    visitas = list(mongo.db.visits.find().sort("created_at", -1))

    resultado = []

    for visita in visitas:

        resultado.append(
            {
                "id": str(visita["_id"]),
                "nombre_visitante": visita.get("nombre_visitante"),
                "telefono": visita.get("telefono"),
                "estado": visita.get("estado"),
                "modalidad": visita.get("modalidad_visita"),
                "fecha_visita": visita.get("fecha_visita"),
                "qr_token": visita.get("qr_token"),
                "qr_estado": visita.get("qr_estado"),
            }
        )

    return jsonify(resultado)
