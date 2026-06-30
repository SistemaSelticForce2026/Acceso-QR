"""
utils/fraccionamientos.py

Manejo central de colecciones por fraccionamiento.

- RESIDENTES: una colección por fraccionamiento.
- VISITAS:    una colección por fraccionamiento.
- Guardias y admins NO se parten: siguen en `users`.
"""

import re
import unicodedata

from bson import ObjectId
from pymongo.errors import PyMongoError

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
    """Normaliza el nombre de un fraccionamiento (sin espacios, minúsculas)."""
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
    """Devuelve {fraccionamiento_norm: nombre_coleccion} de residentes."""

    colecciones = dict(RESIDENTES_COLECCIONES)

    for doc in db.fraccionamientos.find():

        nombre = doc.get("nombre", "").strip()

        if nombre:

            slug = doc.get("slug") or _slug_fraccionamiento(nombre)

            colecciones[_norm(nombre)] = f"residentes_{slug}"

    return colecciones


def visitas_colecciones(db):
    """Devuelve {fraccionamiento_norm: nombre_coleccion} de visitas."""

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
    """Devuelve la lista ordenada de nombres de fraccionamientos."""

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
    """Indica si 'frac' corresponde a un fraccionamiento registrado."""

    return _norm(frac) in residentes_colecciones(db)


# ------------------------------------------------------------------
# Obtener colección específica
# ------------------------------------------------------------------


def coleccion_residentes(db, frac):
    """Devuelve la colección de residentes del fraccionamiento, o None."""

    nombre = residentes_colecciones(db).get(_norm(frac))

    return db[nombre] if nombre else None


def coleccion_visitas(db, frac):
    """Devuelve la colección de visitas del fraccionamiento, o None."""

    nombre = visitas_colecciones(db).get(_norm(frac))

    return db[nombre] if nombre else None


# ------------------------------------------------------------------
# Login
# ------------------------------------------------------------------


def buscar_login(db, correo):
    """Busca al usuario por correo en 'users' y en cada colección de residentes."""

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
    """Indica si el correo ya está registrado en 'users' o en residentes."""

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
    """Busca un residente por su _id recorriendo todas las colecciones."""

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
    """Busca una visita por su token QR en todas las colecciones de visitas."""

    for frac_norm, nombre in visitas_colecciones(db).items():

        doc = db[nombre].find_one({"qr_token": qr_token})

        if doc:
            return doc, frac_norm

    return None, None


# ------------------------------------------------------------------
# Union helper
# ------------------------------------------------------------------


def _union(db, colecciones, pipeline):
    """Ejecuta un pipeline sobre la unión de varias colecciones ($unionWith)."""

    cols = list(colecciones.values())

    if not cols:
        return []

    etapas = [{"$unionWith": {"coll": c}} for c in cols[1:]]

    return db[cols[0]].aggregate(etapas + list(pipeline), allowDiskUse=True)


# ------------------------------------------------------------------
# Aggregations
# ------------------------------------------------------------------


def agg_visitas(db, pipeline):
    """Aplica un pipeline de agregación sobre todas las visitas."""

    return _union(db, visitas_colecciones(db), pipeline)


def agg_residentes(db, pipeline):
    """Aplica un pipeline de agregación sobre todos los residentes."""

    return _union(db, residentes_colecciones(db), pipeline)


# ------------------------------------------------------------------
# Find visitas
# ------------------------------------------------------------------

# Cache de colecciones cuyo índice ya fue asegurado en esta ejecución.
_INDICES_VISITAS_CREADOS = set()


def _asegurar_indices_visitas(db):
    """Crea (una sola vez por colección) el índice por created_at descendente."""
    for nombre in visitas_colecciones(db).values():
        if nombre in _INDICES_VISITAS_CREADOS:
            continue
        try:
            db[nombre].create_index([("created_at", -1)])
            _INDICES_VISITAS_CREADOS.add(nombre)
        except PyMongoError:
            pass


def _cols_visitas(db, frac=None):
    """Colecciones de visitas a consultar.
    Con 'frac' -> solo la de ese fraccionamiento; sin 'frac' -> todas."""
    if frac:
        col = coleccion_visitas(db, frac)
        return [col] if col is not None else []
    return [db[n] for n in visitas_colecciones(db).values()]


def find_visitas(db, filtro=None, sort=None, skip=0, limit=0, frac=None):
    """Busca visitas con filtro/orden/paginación en una o todas las colecciones."""

    filtro = filtro or {}
    sort_list = list(sort) if sort else None

    if sort_list:
        _asegurar_indices_visitas(db)

    need = (skip + limit) if limit else 0

    docs = []
    for col in _cols_visitas(db, frac):
        cur = col.find(filtro)
        if sort_list:
            cur = cur.sort(sort_list)
        if need:
            cur = cur.limit(need)
        docs.extend(cur)

    if sort_list:
        for campo, direccion in reversed(sort_list):
            docs.sort(
                key=lambda d, c=campo: (d.get(c) is not None, d.get(c)),
                reverse=(direccion == -1),
            )

    if limit:
        return docs[skip : skip + limit]
    return docs[skip:] if skip else docs


def contar_visitas(db, filtro=None, frac=None):
    """Cuenta visitas que cumplen el filtro en una o todas las colecciones."""
    filtro = filtro or {}
    total = 0
    for col in _cols_visitas(db, frac):
        total += col.count_documents(filtro)
    return total


# ------------------------------------------------------------------
# Find residentes
# ------------------------------------------------------------------


def find_residentes(db, filtro=None, sort=None, skip=0, limit=0):
    """Busca residentes con filtro/orden/paginación sobre la unión de colecciones."""

    pipe = [{"$match": filtro or {}}]

    if sort:
        pipe.append({"$sort": dict(sort)})

    if skip:
        pipe.append({"$skip": skip})

    if limit:
        pipe.append({"$limit": limit})

    return list(agg_residentes(db, pipe))


def contar_residentes(db, filtro=None):
    """Cuenta residentes que cumplen el filtro en todas las colecciones."""

    filtro = filtro or {}

    total = 0

    for nombre in residentes_colecciones(db).values():

        total += db[nombre].count_documents(filtro)

    return total
