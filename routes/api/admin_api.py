from flask import Blueprint, jsonify
from extensions import mongo
from utils.fraccionamientos import (
    visitas_colecciones,
)

admin_api = Blueprint("admin_api", __name__)


@admin_api.route("/api/admin/dashboard")
def dashboard_api():
    total_visitas = 0
    total_dentro = 0
    total_activas = 0
    total_salidas = 0

    for col_name in visitas_colecciones.values():
        total_visitas += mongo.db[col_name].count_documents({})
        total_dentro += mongo.db[col_name].count_documents({"estado": "dentro"})
        total_activas += mongo.db[col_name].count_documents({"estado": "activo"})
        total_salidas += mongo.db[col_name].count_documents(
            {"estado": "salida_registrada"}
        )

    return jsonify(
        {
            "residentes": mongo.db.users.count_documents({"rol": "residente"}),
            "guardias": mongo.db.users.count_documents({"rol": "guardia"}),
            "visitas": total_visitas,
            "dentro": total_dentro,
            "activas": total_activas,
            "salidas": total_salidas,
            "incidencias": mongo.db.incidencias.count_documents({}),
        }
    )
