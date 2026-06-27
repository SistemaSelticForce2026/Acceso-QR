import re

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
)

from datetime import datetime, timedelta

from pymongo.errors import PyMongoError

from extensions import mongo, socketio

from utils.auth import login_required, role_required
from utils.visita_validacion import validar_acceso_qr, actualizar_qr_vencido_si_aplica

from utils.fraccionamientos import (
    buscar_visita_por_token,
    coleccion_visitas,
    find_visitas,
    contar_visitas,
)

import ast

guard_bp = Blueprint("guard", __name__, url_prefix="/guard")


# ---------------------------------------------------------------------------
# Zona horaria del negocio (Centro de México)
# ---------------------------------------------------------------------------

try:
    from zoneinfo import ZoneInfo

    TZ_LOCAL = ZoneInfo("America/Mexico_City")
except Exception:
    from datetime import timezone

    TZ_LOCAL = timezone(timedelta(hours=-6))


def _ahora_local():
    """Hora actual en la zona del negocio, como datetime naive (para mantener
    consistencia con el resto del sistema, que guarda fechas sin tz)."""
    return datetime.now(TZ_LOCAL).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Constantes del dashboard
# ---------------------------------------------------------------------------
VISITAS_POR_PAGINA = 20
ESTADOS_VALIDOS = {"activo", "dentro", "salida_registrada"}

# Tiempo que el guardia tiene para autorizar (o re-escanear) un QR ya escaneado
# antes de que el pase se marque automáticamente como "No se presentó".
TOLERANCIA_AUTORIZACION = timedelta(minutes=5)


# ---------------------------------------------------------------------------
# Helpers de visitas / QR
# ---------------------------------------------------------------------------


def _col_visita(visita):
    """Devuelve la colección de visitas donde vive esta visita."""
    return coleccion_visitas(mongo.db, visita.get("fraccionamiento"))


def _buscar_visita(token):
    """Busca la visita por token SOLO en la colección del fraccionamiento del guardia."""
    col = coleccion_visitas(mongo.db, session.get("fraccionamiento"))
    if col is None:
        return None
    return col.find_one({"qr_token": token})


def _render_scan(modo, resultado=None, bloquear_camara=False):
    """Renderiza la pantalla de escaneo con el resultado."""
    visita = None
    if resultado and resultado.get("visita"):
        visita = resultado.get("visita")

    return render_template(
        "scanear_qr.html",
        resultado=resultado,
        bloquear_camara=bloquear_camara,
        modo=modo,
        visita=visita,
        form_action=url_for(
            "guard.scan_entrada" if modo == "entrada" else "guard.scan_salida"
        ),
    )


def _normalizar_fotos(visita):
    """Convierte foto_visitante / foto_placa de string a dict (Cloudinary)."""
    if not visita:
        return
    for campo in ("foto_visitante", "foto_placa"):
        if isinstance(visita.get(campo), str):
            try:
                visita[campo] = ast.literal_eval(visita[campo])
            except Exception:
                pass


def _clasificar_razon(mensaje):
    """Convierte el mensaje de validar_acceso_qr en un código de razón
    para que la plantilla muestre la tarjeta correcta."""
    m = (mensaje or "").lower()
    if any(p in m for p in ["venc", "expir", "caduc", "ya pas"]):
        return "fecha_vencida"
    if any(
        p in m
        for p in [
            "futur",
            "aún no",
            "aun no",
            "todavía no",
            "todavia no",
            "próxim",
            "proxim",
            "no inici",
        ]
    ):
        return "fecha_futura"
    if any(
        p in m
        for p in [
            "día no",
            "dia no",
            "no autoriz",
            "no corresponde",
            "fuera de día",
            "fuera de dia",
        ]
    ):
        return "dia_no_autorizado"
    if "horario" in m or "fuera de hora" in m:
        return "fuera_horario"
    return "qr_no_valido"


def _registrar_incidencia_qr(session, tipo, descripcion, visita=None, token=None):
    incidencia = {
        "guardia_id": session["user_id"],
        "guardia_nombre": session["nombre"],
        "tipo_incidencia": tipo,
        "descripcion": descripcion,
        "estado": "abierta",
        "fecha_hora": datetime.now(),
    }
    if visita:
        incidencia["visita_id"] = str(visita["_id"])
        incidencia["visitante"] = visita.get("nombre_visitante")
        incidencia["residencia_destino"] = visita.get("residencia_destino")
    mongo.db.incidencias.insert_one(incidencia)
    socketio.emit("actualizar_dashboard", to="rol:admin")


def _registrar_salida(visita, session):
    ahora = datetime.now()

    mongo.db.access_logs.insert_one(
        {
            "visita_id": str(visita["_id"]),
            "guardia_id": session["user_id"],
            "guardia_nombre": session["nombre"],
            "accion": "salida",
            "fecha_hora": ahora,
            "resultado": "salida_registrada",
            "observaciones": "Salida registrada mediante escaneo QR",
        }
    )

    es_recurrente = visita.get("modalidad_visita") == "recurrente"

    if es_recurrente:
        update_salida = {
            "estado": "activo",
            "hora_salida": ahora.strftime("%H:%M:%S"),
            "fecha_salida": ahora,
        }
    else:
        update_salida = {
            "estado": "salida_registrada",
            "qr_estado": "finalizado",
            "hora_salida": ahora.strftime("%H:%M:%S"),
            "fecha_salida": ahora,
        }

    _col_visita(visita).update_one({"_id": visita["_id"]}, {"$set": update_salida})
    visita.update(update_salida)
    socketio.emit("actualizar_dashboard", to="rol:admin")
    socketio.emit("actualizar_dashboard", to=f"user:{visita['residente_id']}")
    return visita


# ---------------------------------------------------------------------------
# Helpers del dashboard
# ---------------------------------------------------------------------------


def _entero_en_rango(valor, *, por_defecto=1, minimo=1, maximo=None):
    """Convierte un parámetro del querystring a entero acotado a [minimo, maximo]."""
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return por_defecto
    n = max(minimo, n)
    if maximo is not None:
        n = min(maximo, n)
    return n


def _parse_fecha(valor, *, fin_de_dia=False):
    """Parsea 'AAAA-MM-DD'. Devuelve datetime o None si el formato es inválido."""
    if not valor:
        return None
    try:
        fecha = datetime.strptime(valor, "%Y-%m-%d")
    except ValueError:
        return None
    if fin_de_dia:
        fecha = fecha.replace(hour=23, minute=59, second=59, microsecond=999999)
    return fecha


def _construir_filtro_visitas(*, busqueda, f_inicio, f_fin, ver_historial, ahora):
    """Arma el filtro Mongo del listado (sin la pestaña de estado).

    'fecha_visita' se almacena como TEXTO ISO 'YYYY-MM-DD', por eso el rango se
    compara como CADENA (el formato ISO ordena cronológicamente). Comparar
    contra objetos datetime NO funciona: en BSON el texto y las fechas son
    tipos distintos y la comparación nunca coincide.

    - Rango manual: visitas cuya 'fecha_visita' cae dentro del rango.
    - Agenda en vivo (por defecto): de HOY en adelante + pases recurrentes
      (que no tienen fecha fija).
    - Historial completo: de HOY hacia atrás, hasta la primera visita
      registrada. No incluye visitas futuras ni recurrentes sin fecha.
    """
    filtro = {}
    hoy_str = ahora.strftime("%Y-%m-%d")

    if f_inicio or f_fin:
        rango = {}
        if f_inicio:
            rango["$gte"] = f_inicio  # 'YYYY-MM-DD'
        if f_fin:
            rango["$lte"] = f_fin  # 'YYYY-MM-DD'
        filtro["fecha_visita"] = rango

    elif ver_historial:
        filtro["fecha_visita"] = {"$lte": hoy_str}

    else:
        filtro["$or"] = [
            {"fecha_visita": {"$gte": hoy_str}},
            {"modalidad_visita": "recurrente"},
        ]

    if busqueda:
        # re.escape evita que el texto del usuario rompa o inyecte el regex.
        filtro["nombre_visitante"] = {"$regex": re.escape(busqueda), "$options": "i"}

    return filtro


def _listar_visitas(col, filtro, *, modo_orden, hoy_str, skip, limit):
    """Trae la página de visitas ya ordenada según el modo.

    - 'operativo' (vista por defecto): agenda de caseta -> primero las de HOY,
      luego las próximas en orden ascendente, y al final los pases recurrentes
      (sin fecha fija). Es lo que quiere ver el guardia al entrar.
    - 'ascendente' (rango de fechas elegido): cronológico, de la más cercana a
      la más lejana dentro del rango.
    - 'historial': de la más reciente a la más antigua.
    """
    if col is None:
        return []

    pipeline = [{"$match": filtro}]

    if modo_orden == "operativo":
        pipeline += [
            {
                "$addFields": {
                    "_grupo_orden": {
                        "$switch": {
                            "branches": [
                                {
                                    "case": {"$eq": ["$fecha_visita", hoy_str]},
                                    "then": 0,  # hoy
                                },
                                {
                                    "case": {
                                        "$gt": [
                                            {"$ifNull": ["$fecha_visita", ""]},
                                            hoy_str,
                                        ]
                                    },
                                    "then": 1,  # próximas
                                },
                                {
                                    "case": {
                                        "$eq": ["$modalidad_visita", "recurrente"]
                                    },
                                    "then": 2,  # recurrentes sin fecha
                                },
                            ],
                            "default": 3,
                        }
                    }
                }
            },
            {
                "$sort": {
                    "_grupo_orden": 1,
                    "created_at": -1,
                    "fecha_visita": 1,
                    "hora_inicio": 1,
                }
            },
            {"$project": {"_grupo_orden": 0}},
        ]
    elif modo_orden == "historial":
        pipeline += [
            {"$sort": {"fecha_visita": -1, "hora_inicio": -1, "created_at": -1}}
        ]
    else:  # ascendente
        pipeline += [{"$sort": {"fecha_visita": 1, "hora_inicio": 1, "created_at": 1}}]

    pipeline += [{"$skip": skip}, {"$limit": limit}]

    try:
        return list(col.aggregate(pipeline))
    except PyMongoError:
        return []


def _extraer_conteos(col, pipeline, claves):
    """Ejecuta un $facet y devuelve {clave: entero} de forma tolerante a fallos."""
    base = {clave: 0 for clave in claves}
    if col is None:
        return base
    try:
        doc = next(col.aggregate(pipeline), {}) or {}
    except PyMongoError:
        return base
    return {clave: ((doc.get(clave) or [{}])[0].get("n", 0)) for clave in claves}


def _conteos_por_estado(col, filtro_base):
    """Conteos de las pestañas (sobre el filtro base, antes de la pestaña activa)."""
    pipeline = [
        {"$match": filtro_base},
        {
            "$facet": {
                "todas": [{"$count": "n"}],
                "activo": [{"$match": {"estado": "activo"}}, {"$count": "n"}],
                "dentro": [{"$match": {"estado": "dentro"}}, {"$count": "n"}],
                "salida_registrada": [
                    {"$match": {"estado": "salida_registrada"}},
                    {"$count": "n"},
                ],
            }
        },
    ]
    return _extraer_conteos(
        col, pipeline, ("todas", "activo", "dentro", "salida_registrada")
    )


def _conteos_estado_actual(col, inicio_hoy):
    """KPIs operativos: pases activos, visitantes dentro y salidas de hoy."""
    pipeline = [
        {
            "$facet": {
                "activas": [{"$match": {"estado": "activo"}}, {"$count": "n"}],
                "dentro": [{"$match": {"estado": "dentro"}}, {"$count": "n"}],
                "salidas": [
                    {
                        "$match": {
                            "estado": "salida_registrada",
                            "fecha_salida": {"$gte": inicio_hoy},
                        }
                    },
                    {"$count": "n"},
                ],
            }
        }
    ]
    return _extraer_conteos(col, pipeline, ("activas", "dentro", "salidas"))


# ---------------------------------------------------------------------------
# Tolerancia 5 minutos
# ---------------------------------------------------------------------------


def _marcar_no_presentados(col):
    """Marca como 'no_presento' las visitas escaneadas (pendientes de
    autorización) que superaron TOLERANCIA_AUTORIZACION sin ser autorizadas
    ni rechazadas. Los pases recurrentes NO se invalidan: solo se libera el
    estado pendiente y vuelven a quedar 'activo' para un próximo intento."""
    if col is None:
        return
    limite = datetime.now() - TOLERANCIA_AUTORIZACION
    base = {"estado": "pendiente_autorizacion", "fecha_escaneo": {"$lt": limite}}
    try:
        col.update_many(
            {**base, "modalidad_visita": {"$ne": "recurrente"}},
            {"$set": {"estado": "no_presento", "qr_estado": "no_presentado"}},
        )
        col.update_many(
            {**base, "modalidad_visita": "recurrente"},
            {"$set": {"estado": "activo"}},
        )
    except PyMongoError:
        pass


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------


@guard_bp.route("/dashboard")
@login_required
@role_required("guardia")
def dashboard():
    """Panel del guardia: listado paginado de visitas con filtros, búsqueda y KPIs."""

    frac = session.get("fraccionamiento")
    col = coleccion_visitas(mongo.db, frac)
    ahora = datetime.now()

    # Cierra pendientes vencidos (escaneados pero nunca autorizados).
    _marcar_no_presentados(col)

    # --- Parámetros de la petición (validados) ----------------------------
    pagina = _entero_en_rango(request.args.get("page"), por_defecto=1, minimo=1)
    busqueda = request.args.get("busqueda", "").strip()
    estado_sel = request.args.get("estado", "").strip()
    ver_historial = bool(request.args.get("historial"))

    # fecha_visita se guarda como texto ISO 'YYYY-MM-DD', así que el filtro
    # compara como cadena (ver _construir_filtro_visitas). Aquí solo validamos
    # el formato y descartamos lo que venga mal escrito en la URL.
    f_inicio = request.args.get("fecha_inicio", "").strip()
    f_fin = request.args.get("fecha_fin", "").strip()

    fecha_invalida = False
    if f_inicio and _parse_fecha(f_inicio) is None:
        f_inicio, fecha_invalida = "", True
    if f_fin and _parse_fecha(f_fin) is None:
        f_fin, fecha_invalida = "", True
    if fecha_invalida:
        flash("Formato de fecha inválido. Usa AAAA-MM-DD.", "warning")

    if estado_sel and estado_sel not in ESTADOS_VALIDOS:
        estado_sel = ""  # descarta valores manipulados en la URL

    # --- Filtro base (sin la pestaña de estado) ---------------------------
    filtro = _construir_filtro_visitas(
        busqueda=busqueda,
        f_inicio=f_inicio,
        f_fin=f_fin,
        ver_historial=ver_historial,
        ahora=ahora,
    )

    # Conteos de pestañas: una sola consulta sobre el filtro base.
    conteo = _conteos_por_estado(col, filtro)

    # --- Pestaña activa ----------------------------------------------------
    if estado_sel:
        filtro = {**filtro, "estado": estado_sel}
        total_visitas = conteo.get(estado_sel, 0)
    else:
        total_visitas = conteo["todas"]

    # --- Paginación segura -------------------------------------------------
    total_paginas = max(
        1, (total_visitas + VISITAS_POR_PAGINA - 1) // VISITAS_POR_PAGINA
    )
    pagina = min(pagina, total_paginas)

    # Modo de orden: el historial manda (más reciente primero); si hay un rango
    # elegido fuera del historial, cronológico ascendente; si no, agenda de hoy.
    if ver_historial:
        modo_orden = "historial"
    elif f_inicio or f_fin:
        modo_orden = "ascendente"
    else:
        modo_orden = "operativo"

    hoy_str = ahora.strftime("%Y-%m-%d")

    visitas = _listar_visitas(
        col,
        filtro,
        modo_orden=modo_orden,
        hoy_str=hoy_str,
        skip=(pagina - 1) * VISITAS_POR_PAGINA,
        limit=VISITAS_POR_PAGINA,
    )

    # --- KPIs operativos (estado actual del fraccionamiento) --------------
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    kpis = _conteos_estado_actual(col, inicio_hoy)

    incidencias = mongo.db.incidencias.count_documents({"estado": "abierta"})

    return render_template(
        "guardia_dashboard.html",
        visitas=visitas,
        hoy=ahora.strftime("%Y-%m-%d"),
        activas=kpis["activas"],
        dentro=kpis["dentro"],
        salidas=kpis["salidas"],
        incidencias=incidencias,
        pagina=pagina,
        total_paginas=total_paginas,
        total_visitas=total_visitas,
        conteo=conteo,
        estado_sel=estado_sel,
        fecha_inicio=f_inicio,
        fecha_fin=f_fin,
        busqueda=busqueda,
        ver_historial=ver_historial,
    )


@guard_bp.route("/scan")
@login_required
@role_required("guardia")
def scan():
    return redirect(url_for("guard.scan_entrada"))


# ---------------------------------------------------------------------------
# ESCANEO DE ENTRADA  (SOLO LECTURA — no consume hasta autorizar)
# ---------------------------------------------------------------------------


@guard_bp.route("/scan/entrada", methods=["GET", "POST"])
@login_required
@role_required("guardia")
def scan_entrada():

    resultado = None

    _marcar_no_presentados(coleccion_visitas(mongo.db, session.get("fraccionamiento")))

    if request.method == "POST":
        token = request.form["qr_token"].strip()
        visita = _buscar_visita(token)
        _normalizar_fotos(visita)

        if not visita:
            _registrar_incidencia_qr(
                session,
                "qr_no_encontrado",
                f"Entrada: QR no registrado. Token: {token}",
            )
            resultado = {
                "estado": "rechazado",
                "razon": "qr_no_encontrado",
                "mensaje": "QR no encontrado. Incidencia registrada automáticamente.",
            }

        elif (
            visita.get("qr_estado") == "rechazado"
            or visita.get("estado") == "rechazado"
        ):
            # Ya fue rechazado antes: NO registramos otra incidencia,
            # solo informamos que el pase quedó rechazado.
            resultado = {
                "estado": "rechazado",
                "razon": "qr_rechazado",
                "mensaje": "Este QR fue rechazado por el guardia y ya no puede utilizarse.",
                "visita": visita,
                "fecha_visita": visita.get("fecha_visita"),
            }

        elif visita.get("qr_estado") in ["vencido", "cancelado", "finalizado"]:
            _registrar_incidencia_qr(
                session,
                "qr_no_valido",
                f"Entrada: QR con estado {visita.get('qr_estado')}",
                visita=visita,
            )
            _razon_qr = {
                "vencido": "fecha_vencida",
                "cancelado": "qr_cancelado",
                "finalizado": "qr_finalizado",
            }.get(visita.get("qr_estado"), "qr_finalizado")
            resultado = {
                "estado": "rechazado",
                "razon": _razon_qr,
                "mensaje": "Este QR ya no es válido o fue finalizado.",
                "visita": visita,
                "fecha_visita": visita.get("fecha_visita"),
            }

        elif visita.get("estado") == "dentro":
            resultado = {
                "estado": "rechazado",
                "razon": "ya_dentro",
                "mensaje": "Este visitante ya está dentro. Use el escáner de salida.",
                "visita": visita,
            }

        elif (
            visita.get("estado") == "no_presento"
            or visita.get("qr_estado") == "no_presentado"
        ):
            resultado = {
                "estado": "rechazado",
                "razon": "qr_no_valido",
                "mensaje": "Este pase se marcó como “No se presentó” por superar el tiempo de tolerancia y ya no es válido.",
                "visita": visita,
                "fecha_visita": visita.get("fecha_visita"),
            }

        else:
            actualizar_qr_vencido_si_aplica(visita["_id"], visita)
            visita = _buscar_visita(token)
            _normalizar_fotos(visita)

            valido, mensaje_val = validar_acceso_qr(visita)

            if not valido:
                _registrar_incidencia_qr(
                    session,
                    "qr_no_valido",
                    f"Entrada: {mensaje_val}",
                    visita=visita,
                )
                resultado = {
                    "estado": "rechazado",
                    "razon": _clasificar_razon(mensaje_val),
                    "mensaje": mensaje_val,
                    "visita": visita,
                    "fecha_visita": visita.get("fecha_visita"),
                }

            else:
                # El QR es válido. Persistimos "pendiente de autorización" junto
                # con la hora del escaneo. Así, si la pantalla se refresca por
                # error, el guardia tiene TOLERANCIA_AUTORIZACION (5 min) para
                # volver a escanear el mismo QR. Pasado ese tiempo sin autorizar,
                # _marcar_no_presentados() lo marca como "no_presento".
                # No se consume el pase: 'entrada_consumida' sigue en False y el
                # estado real solo pasa a "dentro" al pulsar "Autorizar acceso".
                ahora = datetime.now()
                _col_visita(visita).update_one(
                    {"_id": visita["_id"]},
                    {
                        "$set": {
                            "estado": "pendiente_autorizacion",
                            "hora_escaneo": ahora.strftime("%H:%M:%S"),
                            "fecha_escaneo": ahora,
                        }
                    },
                )
                visita["estado"] = "pendiente_autorizacion"
                visita["hora_escaneo"] = ahora.strftime("%H:%M:%S")
                visita["fecha_escaneo"] = ahora

                resultado = {
                    "estado": "permitido",
                    "mensaje": "QR validado correctamente. Esperando autorización del guardia.",
                    "visita": visita,
                }

    bloquear = resultado and resultado.get("estado") in ("permitido", "incidencia")
    return _render_scan("entrada", resultado, bloquear_camara=bloquear)


# ---------------------------------------------------------------------------
# ESCANEO DE SALIDA
# ---------------------------------------------------------------------------


@guard_bp.route("/scan/salida", methods=["GET", "POST"])
@login_required
@role_required("guardia")
def scan_salida():

    resultado = None

    if request.method == "POST":
        token = request.form["qr_token"].strip()
        visita = _buscar_visita(token)
        _normalizar_fotos(visita)

        if not visita:
            _registrar_incidencia_qr(
                session,
                "qr_no_encontrado",
                f"Salida: QR no registrado. Token: {token}",
            )
            resultado = {
                "estado": "rechazado",
                "razon": "qr_no_encontrado",
                "mensaje": "QR no encontrado. Incidencia registrada automáticamente.",
            }

        elif visita.get("estado") != "dentro":
            resultado = {
                "estado": "rechazado",
                "razon": "no_dentro",
                "mensaje": "Este visitante no está dentro del fraccionamiento. Use el escáner de entrada.",
                "visita": visita,
            }

        else:
            visita = _registrar_salida(visita, session)
            resultado = {
                "estado": "salida_registrada",
                "mensaje": "Salida registrada correctamente.",
                "visita": visita,
            }

    bloquear = resultado and resultado.get("estado") in (
        "salida_registrada",
        "incidencia",
    )
    return _render_scan("salida", resultado, bloquear_camara=bloquear)


# ---------------------------------------------------------------------------
# INCIDENCIA MANUAL (RECHAZO)
# ---------------------------------------------------------------------------


@guard_bp.route("/incidencia-manual", methods=["POST"])
@login_required
@role_required("guardia")
def incidencia_manual():

    token = request.form.get("qr_token", "").strip()
    modo = request.form.get("modo", "entrada")
    tipo_incidencia = request.form["tipo_incidencia"]
    detalle = request.form.get("detalle", "").strip()

    visita = _buscar_visita(token) if token else None

    descripciones = {
        "placa_no_coincide": "La placa del vehículo no coincide con la registrada.",
        "persona_sospechosa": "Se detectó una persona con comportamiento sospechoso.",
        "visitante_agresivo": "El visitante presentó una actitud agresiva.",
        "datos_no_coinciden": "Los datos del visitante no coinciden con la información registrada.",
        "sin_autorizacion": "La persona intenta ingresar sin autorización.",
    }

    descripcion_base = descripciones.get(
        tipo_incidencia, "Incidencia registrada por el guardia."
    )
    descripcion = (
        f"{descripcion_base} {detalle}".strip() if detalle else descripcion_base
    )

    _registrar_incidencia_qr(
        session,
        tipo_incidencia,
        descripcion,
        visita=visita,
    )

    if visita:
        ahora = datetime.now()
        update_rechazo = {
            "estado": "rechazado",
            "qr_estado": "rechazado",
            "motivo_rechazo": tipo_incidencia,
            "detalle_rechazo": detalle,
            "fecha_rechazo": ahora,
            "rechazado_por": session.get("nombre"),
        }
        _col_visita(visita).update_one({"_id": visita["_id"]}, {"$set": update_rechazo})
        visita.update(update_rechazo)

        # Bitácora de accesos (para que el dashboard admin lo cuente
        # como "rechazado": logs con resultado == "rechazado").
        mongo.db.access_logs.insert_one(
            {
                "visita_id": str(visita["_id"]),
                "guardia_id": session["user_id"],
                "guardia_nombre": session["nombre"],
                "accion": "rechazo",
                "fecha_hora": ahora,
                "resultado": "rechazado",
                "observaciones": descripcion,
            }
        )

        # Avisar a admin y al residente dueño del pase.
        socketio.emit("actualizar_dashboard", to="rol:admin")
        if visita.get("residente_id"):
            socketio.emit("actualizar_dashboard", to=f"user:{visita['residente_id']}")

    resultado = {
        "estado": "incidencia",
        "mensaje": "Incidencia registrada correctamente.",
        "visita": visita,
        "incidencia": descripcion,
    }

    return _render_scan(modo, resultado, bloquear_camara=True)


# ---------------------------------------------------------------------------
# AUTORIZAR ACCESO (aquí SÍ se consume / cambia el estado)
# ---------------------------------------------------------------------------


@guard_bp.route("/confirm-access", methods=["POST"])
@login_required
@role_required("guardia")
def confirm_access():

    token = request.form["qr_token"]
    visita = _buscar_visita(token)

    if visita:

        ahora = datetime.now()

        update_entrada = {
            "estado": "dentro",
            "hora_entrada_real": ahora.strftime("%H:%M:%S"),
            "fecha_entrada_real": ahora,
            "hora_escaneo": ahora.strftime("%H:%M:%S"),
            "fecha_escaneo": ahora,
        }

        if visita.get("modalidad_visita", "temporal") == "temporal":
            update_entrada["entrada_consumida"] = True  # se consume al autorizar
        else:
            # Recurrente: limpiar el ciclo del día anterior
            update_entrada["hora_salida"] = None
            update_entrada["fecha_salida"] = None

        _col_visita(visita).update_one({"_id": visita["_id"]}, {"$set": update_entrada})

        mongo.db.access_logs.insert_one(
            {
                "visita_id": str(visita["_id"]),
                "guardia_id": session["user_id"],
                "guardia_nombre": session["nombre"],
                "accion": "confirmacion_manual",
                "fecha_hora": ahora,
                "resultado": "acceso_confirmado",
                "observaciones": "Guardia confirmó físicamente al visitante",
            }
        )

        socketio.emit("actualizar_dashboard", to="rol:admin")
        socketio.emit("actualizar_dashboard", to=f"user:{visita['residente_id']}")

    flash("Acceso autorizado correctamente.", "success")

    return redirect(url_for("guard.dashboard"))
