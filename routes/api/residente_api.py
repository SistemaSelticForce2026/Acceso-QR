from flask import Blueprint, jsonify
from extensions import mongo
from utils.fraccionamientos import visitas_colecciones

residente_api = Blueprint("residente_api", __name__)


@residente_api.route("/api/residente/visitas")
def obtener_visitas():

    resultado = []

    # Recorre las 3 colecciones de visitas (una por fraccionamiento)
    for nombre in VISITAS_COLECCIONES.values():

        for visita in mongo.db[nombre].find().sort("created_at", -1):

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
