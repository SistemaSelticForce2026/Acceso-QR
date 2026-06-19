"""
utils/fraccionamientos.py

Manejo central de colecciones por fraccionamiento.

- RESIDENTES: una colección por fraccionamiento.
- VISITAS:    una colección por fraccionamiento.
- Guardias y admins NO se parten: siguen en `users`.
"""

from bson import ObjectId
import re
import unicodedata

# ------------------------------------------------------------------
# Fraccionamientos base del sistema
# ------------------------------------------------------------------

FRACCIONAMIENTOS = [
    "foresta dream lagons",
    "cedro zinacantepec",
    "villas del bosque ii",
]

FRACCIONAMIENTOS_LABELS = {
    "foresta dream lagons": "Foresta Dream Lagons",
    "cedro zinacantepec": "Cedro Zinacantepec",
    "villas del bosque ii": "Villas del Bosque II",
}

# Compatibilidad con código existente
RESIDENTES_COLECCIONES = {
    "foresta dream lagons": "residentes_foresta_dream_lagons",
    "cedro zinacantepec": "residentes_cedro_zinacantepec",
    "villas del bosque ii": "residentes_villas_del_bosque_ii",
}

VISITAS_COLECCIONES = {
    "foresta dream lagons": "visitas_foresta_dream_lagons",
    "cedro zinacantepec": "visitas_cedro_zinacantepec",
    "villas del bosque ii": "visitas_villas_del_bosque_ii",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _norm(frac):
    return (frac or "").strip().lower()


def _slug_fraccionamiento(nombre):
    """
    Villas del Bosque II
    ->
    villas_del_bosque_ii
    """

    s = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()

    s = re.sub(r"[^a-z0-9]+", "_", s.lower().strip()).strip("_")

    return s


# ------------------------------------------------------------------
# Colecciones dinámicas
# ------------------------------------------------------------------


def residentes_colecciones(db):

    colecciones = dict(RESIDENTES_COLECCIONES)

    for doc in db.fraccionamientos.find():

        nombre = doc.get("nombre", "").strip()

        if nombre:

            slug = doc.get("slug") or _slug_fraccionamiento(nombre)

            colecciones[_norm(nombre)] = f"residentes_{slug}"

    return colecciones


def visitas_colecciones(db):

    colecciones = {}

    # Fraccionamientos base
    for nombre in FRACCIONAMIENTOS:

        slug = _slug_fraccionamiento(nombre)

        colecciones[_norm(nombre)] = f"visitas_{slug}"

    # Fraccionamientos creados desde admin
    if "fraccionamientos" in db.list_collection_names():

        for doc in db.fraccionamientos.find():

            nombre = (doc.get("nombre") or "").strip()

            if not nombre:
                continue

            slug = doc.get("slug") or _slug_fraccionamiento(nombre)

            colecciones[_norm(nombre)] = f"visitas_{slug}"

    return colecciones


# ------------------------------------------------------------------
# Lista completa de fraccionamientos
# ------------------------------------------------------------------


def obtener_fraccionamientos(db):

    nombres = list(FRACCIONAMIENTOS)

    if "fraccionamientos" in db.list_collection_names():

        for doc in db.fraccionamientos.find():

            nombre = (doc.get("nombre") or "").strip()

            if nombre and nombre not in nombres:

                nombres.append(nombre)

    return sorted(nombres)


# ------------------------------------------------------------------
# Validación
# ------------------------------------------------------------------


def es_fraccionamiento_valido(db, frac):

    return _norm(frac) in residentes_colecciones(db)


# ------------------------------------------------------------------
# Obtener colección específica
# ------------------------------------------------------------------


def coleccion_residentes(db, frac):

    nombre = residentes_colecciones(db).get(_norm(frac))

    return db[nombre] if nombre else None


def coleccion_visitas(db, frac):

    nombre = visitas_colecciones(db).get(_norm(frac))

    return db[nombre] if nombre else None


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------


def buscar_login(db, correo):

    correo = (correo or "").strip()

    usuario = db.users.find_one({"correo": correo})

    if usuario:
        return usuario, db.users

    for nombre in residentes_colecciones(db).values():

        doc = db[nombre].find_one({"correo": correo})

        if doc:
            return doc, db[nombre]

    return None, None


# ------------------------------------------------------------------
# Correo existente
# ------------------------------------------------------------------


def correo_ya_existe(db, correo):

    correo = (correo or "").strip()

    if db.users.find_one({"correo": correo}):
        return True

    for nombre in residentes_colecciones(db).values():

        if db[nombre].find_one({"correo": correo}):

            return True

    return False


# ------------------------------------------------------------------
# Buscar residente por ID
# ------------------------------------------------------------------


def buscar_residente_por_id(db, residente_id):

    if isinstance(residente_id, str):

        residente_id = ObjectId(residente_id)

    for nombre in residentes_colecciones(db).values():

        doc = db[nombre].find_one({"_id": residente_id})

        if doc:
            return doc, db[nombre]

    return None, None


# ------------------------------------------------------------------
# Buscar visita por token QR
# ------------------------------------------------------------------


def buscar_visita_por_token(db, qr_token):

    for frac_norm, nombre in visitas_colecciones(db).items():

        doc = db[nombre].find_one({"qr_token": qr_token})

        if doc:
            return doc, frac_norm

    return None, None


# ------------------------------------------------------------------
# Union helper
# ------------------------------------------------------------------


def _union(db, colecciones, pipeline):

    cols = list(colecciones.values())

    if not cols:
        return []

    etapas = [{"$unionWith": {"coll": c}} for c in cols[1:]]

    return db[cols[0]].aggregate(etapas + list(pipeline))


# ------------------------------------------------------------------
# Aggregations
# ------------------------------------------------------------------


def agg_visitas(db, pipeline):

    return _union(db, visitas_colecciones(db), pipeline)


def agg_residentes(db, pipeline):

    return _union(db, residentes_colecciones(db), pipeline)


# ------------------------------------------------------------------
# Find visitas
# ------------------------------------------------------------------


def find_visitas(db, filtro=None, sort=None, skip=0, limit=0):

    pipe = [{"$match": filtro or {}}]

    if sort:
        pipe.append({"$sort": dict(sort)})

    if skip:
        pipe.append({"$skip": skip})

    if limit:
        pipe.append({"$limit": limit})

    return list(agg_visitas(db, pipe))


def contar_visitas(db, filtro=None):

    filtro = filtro or {}

    total = 0

    for nombre in visitas_colecciones(db).values():

        total += db[nombre].count_documents(filtro)

    return total


# ------------------------------------------------------------------
# Find residentes
# ------------------------------------------------------------------


def find_residentes(db, filtro=None, sort=None, skip=0, limit=0):

    pipe = [{"$match": filtro or {}}]

    if sort:
        pipe.append({"$sort": dict(sort)})

    if skip:
        pipe.append({"$skip": skip})

    if limit:
        pipe.append({"$limit": limit})

    return list(agg_residentes(db, pipe))


def contar_residentes(db, filtro=None):

    filtro = filtro or {}

    total = 0

    for nombre in residentes_colecciones(db).values():

        total += db[nombre].count_documents(filtro)

    return total
