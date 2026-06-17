"""
Reparte el created_at de las VISITAS DE PRUEBA en los últimos 180 días.

Por qué: el seed las guardó todas con created_at = ahora, así que el
dashboard procesaba las 20000 en cada carga. Tras esto, el filtro "hoy"
solo toca las de las últimas 24h y carga rápido.

Solo afecta datos de prueba (es_prueba = True; con respaldo para el seed
viejo que usaba qr_path dummy-qr.com). NO toca visitas reales.

    python scripts\\repartir_fechas_visitas.py
"""

from pymongo import MongoClient

MONGO_URI = "mongodb+srv://software_db_user:M22TlbYUEJCo7lXh@accesoqr.zopq4ja.mongodb.net/?appName=accesoqr"

client = MongoClient(MONGO_URI)
db = client["accesoqr"]

try:
    client.admin.command("ping")
    print("Conexión a MongoDB OK\n")
except Exception as e:
    print("No se pudo conectar a MongoDB:", e)
    raise SystemExit(1)

DIAS = 180
MINUTOS = DIAS * 24 * 60

# Solo datos de prueba (marcador nuevo + respaldo del seed viejo)
filtro = {
    "$or": [
        {"es_prueba": True},
        {"qr_path": {"$regex": "dummy-qr.com"}},
    ]
}

total = db.visits.count_documents(filtro)
print(f"Visitas de prueba a repartir: {total}")
print(f"Rango: últimos {DIAS} días\n")

# created_at = ahora - (aleatorio * 180 días), por documento
resultado = db.visits.update_many(
    filtro,
    [
        {
            "$set": {
                "created_at": {
                    "$dateSubtract": {
                        "startDate": "$$NOW",
                        "unit": "minute",
                        "amount": {"$toInt": {"$multiply": [{"$rand": {}}, MINUTOS]}},
                    }
                }
            }
        }
    ],
)

print(f"Visitas actualizadas: {resultado.modified_count}")
print("\nListo. Ahora el dashboard 'hoy' solo verá las de las últimas 24h.")
