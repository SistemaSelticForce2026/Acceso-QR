from flask import Blueprint, jsonify
from extensions import mongo

reportes_api = Blueprint("reportes_api", __name__)


@reportes_api.route("/api/reportes")
def reportes():

    return jsonify(
        {
            "visitas": mongo.db.visits.count_documents({}),
            "accesos": mongo.db.access_logs.count_documents({}),
            "incidencias": mongo.db.incidencias.count_documents({}),
        }
    )
