from flask import Blueprint, jsonify
from extensions import mongo

admin_api = Blueprint("admin_api", __name__)


@admin_api.route("/api/admin/dashboard")
def dashboard_api():

    return jsonify(
        {
            "residentes": mongo.db.users.count_documents({"rol": "residente"}),
            "guardias": mongo.db.users.count_documents({"rol": "guardia"}),
            "visitas": mongo.db.visits.count_documents({}),
            "dentro": mongo.db.visits.count_documents({"estado": "dentro"}),
            "activas": mongo.db.visits.count_documents({"estado": "activo"}),
            "salidas": mongo.db.visits.count_documents({"estado": "salida_registrada"}),
            "incidencias": mongo.db.incidencias.count_documents({}),
        }
    )
