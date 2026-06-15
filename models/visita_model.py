def visit_schema(data):
    return {
        "residente_id": data.get("residente_id"),
        "nombre_visitante": data.get("nombre_visitante"),
        "telefono": data.get("telefono"),
        "modalidad_visita": data.get("modalidad_visita", "temporal"),
        "motivo": data.get("motivo"),
        "residencia_destino": data.get("residencia_destino"),
        "foto_placa": data.get("foto_placa"),
        "estado": "activo",
    }
