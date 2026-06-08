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

from extensions import mongo, socketio

from utils.auth import login_required, role_required
from utils.visita_validacion import validar_acceso_qr, actualizar_qr_vencido_si_aplica

import ast

guard_bp = Blueprint("guard", __name__, url_prefix="/guard")


def _render_scan(modo, resultado=None, bloquear_camara=False):

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

    mongo.db.visits.update_one({"_id": visita["_id"]}, {"$set": update_salida})
    visita.update(update_salida)
    return visita


@guard_bp.route("/dashboard")
@login_required
@role_required("guardia")
def dashboard():

    # =============================================
    # PAGINACION
    # =============================================

    pagina = int(request.args.get("page", 1))

    por_pagina = 5

    busqueda = request.args.get("busqueda", "").strip()

    fecha_inicio = request.args.get("fecha_inicio", "").strip()

    fecha_fin = request.args.get("fecha_fin", "").strip()

    filtro = {}

    if fecha_inicio:
        filtro["fecha_visita"] = {"$gte": fecha_inicio}

    if fecha_fin:
        filtro.setdefault("fecha_visita", {})
        filtro["fecha_visita"]["$lte"] = fecha_fin

    if busqueda:
        filtro["nombre_visitante"] = {"$regex": busqueda, "$options": "i"}

    total_visitas = mongo.db.visits.count_documents(filtro)

    total_paginas = (total_visitas + por_pagina - 1) // por_pagina

    visitas = list(
        mongo.db.visits.find(filtro)
        .sort("created_at", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    activas = mongo.db.visits.count_documents({"estado": "activo"})
    dentro = mongo.db.visits.count_documents({"estado": "dentro"})
    salidas = mongo.db.visits.count_documents({"estado": "salida_registrada"})
    incidencias = mongo.db.incidencias.count_documents({})

    print("\n===== PAGINA 1 =====")

    for v in visitas:

        print(v.get("nombre_visitante"), v.get("created_at"))

    print("===================\n")

    return render_template(
        "guardia_dashboard.html",
        visitas=visitas,
        activas=activas,
        dentro=dentro,
        salidas=salidas,
        incidencias=incidencias,
        pagina=pagina,
        total_paginas=total_paginas,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        busqueda=busqueda,
    )


@guard_bp.route("/scan")
@login_required
@role_required("guardia")
def scan():
    return redirect(url_for("guard.scan_entrada"))


@guard_bp.route("/scan/entrada", methods=["GET", "POST"])
@login_required
@role_required("guardia")
def scan_entrada():

    resultado = None

    if request.method == "POST":
        token = request.form["qr_token"].strip()
        visita = mongo.db.visits.find_one({"qr_token": token})

        # =====================================
        # NORMALIZAR FOTOS CLOUDINARY
        # =====================================

        if visita:

            if isinstance(visita.get("foto_visitante"), str):

                try:
                    visita["foto_visitante"] = ast.literal_eval(
                        visita["foto_visitante"]
                    )
                except:
                    pass

            if isinstance(visita.get("foto_placa"), str):

                try:
                    visita["foto_placa"] = ast.literal_eval(visita["foto_placa"])
                except:
                    pass

        if not visita:
            _registrar_incidencia_qr(
                session,
                "qr_no_encontrado",
                f"Entrada: QR no registrado. Token: {token}",
            )
            resultado = {
                "estado": "rechazado",
                "mensaje": "QR no encontrado. Incidencia registrada automáticamente.",
            }

        elif visita.get("qr_estado") in ["vencido", "cancelado", "finalizado"]:
            _registrar_incidencia_qr(
                session,
                "qr_no_valido",
                f"Entrada: QR con estado {visita.get('qr_estado')}",
                visita=visita,
            )
            resultado = {
                "estado": "rechazado",
                "mensaje": "QR no válido o ya finalizado.",
            }

        elif visita.get("estado") == "dentro":
            resultado = {
                "estado": "rechazado",
                "mensaje": "Este visitante ya está dentro. Use el escáner de salida.",
                "visita": visita,
            }

        else:
            actualizar_qr_vencido_si_aplica(visita["_id"], visita)
            visita = mongo.db.visits.find_one({"qr_token": token})

            # =====================================
            # NORMALIZAR FOTOS CLOUDINARY
            # =====================================

            if visita:

                if isinstance(visita.get("foto_visitante"), str):

                    try:
                        visita["foto_visitante"] = ast.literal_eval(
                            visita["foto_visitante"]
                        )
                    except:
                        pass

                if isinstance(visita.get("foto_placa"), str):

                    try:
                        visita["foto_placa"] = ast.literal_eval(visita["foto_placa"])
                    except:
                        pass

            valido, mensaje_val = validar_acceso_qr(visita)

            if not valido:
                _registrar_incidencia_qr(
                    session,
                    "qr_no_valido",
                    f"Entrada: {mensaje_val}",
                    visita=visita,
                )
                resultado = {"estado": "rechazado", "mensaje": mensaje_val}

            else:
                ahora = datetime.now()
                update_entrada = {
                    "estado": "pendiente_autorizacion",
                    "hora_escaneo": ahora.strftime("%H:%M:%S"),
                    "fecha_escaneo": ahora,
                }
                if visita.get("modalidad_visita", "temporal") == "temporal":
                    update_entrada["entrada_consumida"] = True

                mongo.db.access_logs.insert_one(
                    {
                        "visita_id": str(visita["_id"]),
                        "guardia_id": session["user_id"],
                        "guardia_nombre": session["nombre"],
                        "accion": "entrada",
                        "fecha_hora": ahora,
                        "resultado": "permitido",
                        "observaciones": "Entrada autorizada por QR",
                    }
                )
                mongo.db.visits.update_one(
                    {"_id": visita["_id"]}, {"$set": update_entrada}
                )

                visita["estado"] = "pendiente_autorizacion"
                visita["hora_escaneo"] = ahora.strftime("%H:%M:%S")

                resultado = {
                    "estado": "permitido",
                    "mensaje": "QR validado correctamente. Esperando autorización del guardia.",
                    "visita": visita,
                }

    bloquear = resultado and resultado.get("estado") in ("permitido", "incidencia")
    return _render_scan("entrada", resultado, bloquear_camara=bloquear)


@guard_bp.route("/scan/salida", methods=["GET", "POST"])
@login_required
@role_required("guardia")
def scan_salida():

    resultado = None

    if request.method == "POST":

        token = request.form["qr_token"].strip()

        visita = mongo.db.visits.find_one({"qr_token": token})

        # =====================================
        # NORMALIZAR FOTOS CLOUDINARY
        # =====================================

        if visita:

            if isinstance(visita.get("foto_visitante"), str):

                try:
                    visita["foto_visitante"] = ast.literal_eval(
                        visita["foto_visitante"]
                    )
                except:
                    pass

            if isinstance(visita.get("foto_placa"), str):

                try:
                    visita["foto_placa"] = ast.literal_eval(visita["foto_placa"])
                except:
                    pass

        if not visita:
            _registrar_incidencia_qr(
                session,
                "qr_no_encontrado",
                f"Salida: QR no registrado. Token: {token}",
            )
            resultado = {
                "estado": "rechazado",
                "mensaje": "QR no encontrado. Incidencia registrada automáticamente.",
            }

        elif visita.get("estado") != "dentro":
            resultado = {
                "estado": "rechazado",
                "mensaje": "Este visitante no está registrado como dentro. Use el escáner de entrada.",
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


@guard_bp.route("/incidencia-manual", methods=["POST"])
@login_required
@role_required("guardia")
def incidencia_manual():

    token = request.form.get("qr_token", "").strip()
    modo = request.form.get("modo", "entrada")
    tipo_incidencia = request.form["tipo_incidencia"]

    visita = mongo.db.visits.find_one({"qr_token": token}) if token else None

    descripciones = {
        "placa_no_coincide": "La placa del vehículo no coincide con la registrada.",
        "persona_sospechosa": "Se detectó una persona con comportamiento sospechoso.",
        "visitante_agresivo": "El visitante presentó una actitud agresiva.",
        "datos_no_coinciden": "Los datos del visitante no coinciden con la información registrada.",
        "sin_autorizacion": "La persona intenta ingresar sin autorización.",
    }

    _registrar_incidencia_qr(
        session,
        tipo_incidencia,
        descripciones.get(tipo_incidencia, "Incidencia registrada por el guardia."),
        visita=visita,
    )

    resultado = {
        "estado": "incidencia",
        "mensaje": "Incidencia registrada correctamente.",
        "visita": visita,
        "incidencia": descripciones.get(tipo_incidencia),
    }

    return _render_scan(modo, resultado, bloquear_camara=True)


@guard_bp.route("/exit", methods=["POST"])
@login_required
@role_required("guardia")
def register_exit():
    return redirect(url_for("guard.scan_salida"))


@guard_bp.route("/confirm-access", methods=["POST"])
@login_required
@role_required("guardia")
def confirm_access():

    token = request.form["qr_token"]
    visita = mongo.db.visits.find_one({"qr_token": token})

    if visita:

        mongo.db.visits.update_one(
            {"_id": visita["_id"]},
            {
                "$set": {
                    "estado": "dentro",
                    "hora_entrada_real": datetime.now().strftime("%H:%M:%S"),
                    "fecha_entrada_real": datetime.now(),
                }
            },
        )

        mongo.db.access_logs.insert_one(
            {
                "visita_id": str(visita["_id"]),
                "guardia_id": session["user_id"],
                "guardia_nombre": session["nombre"],
                "accion": "confirmacion_manual",
                "fecha_hora": datetime.now(),
                "resultado": "acceso_confirmado",
                "observaciones": "Guardia confirmó físicamente al visitante",
            }
        )

    flash("Acceso autorizado correctamente.", "success")

    return redirect(url_for("guard.dashboard"))
