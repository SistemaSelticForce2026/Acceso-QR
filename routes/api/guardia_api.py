from flask import Blueprint, request, jsonify
from extensions import mongo
from utils.fraccionamientos import visitas_colecciones

guardia_api = Blueprint("guardia_api", __name__)


@guardia_api.route("/api/guardia/validar-qr", methods=["GET", "POST"])
def validar_qr():
    if request.method == "GET":
        return jsonify({"mensaje": "API QR funcionando"})

    token = request.json.get("token")
    visita = None

    for col_name in visitas_colecciones.values():
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
