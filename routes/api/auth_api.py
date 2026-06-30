"""Endpoints de API de autenticación (prueba de disponibilidad)."""

# pylint: disable=missing-function-docstring

from flask import Blueprint, jsonify

auth_api = Blueprint("auth_api", __name__)


@auth_api.route("/api/test")
def api_test():
    return jsonify({"success": True, "mensaje": "API funcionando"})
