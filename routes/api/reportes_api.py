from flask import Blueprint, jsonify
from extensions import mongo
from utils.fraccionamientos import visitas_colecciones

reportes_api = Blueprint("reportes_api", __name__)


@reportes_api.route("/api/reportes")
def reportes():
    total_visitas = 0
    for col_name in visitas_colecciones.values():
        total_visitas += mongo.db[col_name].count_documents({})

    return jsonify(
        {
            "visitas": total_visitas,
            "accesos": mongo.db.access_logs.count_documents({}),
            "incidencias": mongo.db.incidencias.count_documents({}),
        }
    )
