"""Rutas del residente: dashboard, visitantes, creación y edición de visitas."""

import uuid
from datetime import datetime, timedelta

from bson import ObjectId
from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from extensions import mongo, socketio
from utils.auth import login_required, role_required
from utils.fraccionamientos import coleccion_residentes, coleccion_visitas
from utils.qr_generator import generate_qr
from utils.uploads import guardar_imagen

resident_bp = Blueprint("resident", __name__, url_prefix="/resident")


@resident_bp.after_request
def no_cache(response):
    """Evita que el navegador cachee las páginas del residente."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# =====================================================
# HELPERS DE COLECCIÓN (según el fraccionamiento del residente logueado)
# =====================================================


def _frac_actual():
    """Fraccionamiento del residente logueado (se guarda en sesión al hacer login)."""
    return session.get("fraccionamiento")


def _mis_visitas():
    """Colección de visitas del fraccionamiento del residente logueado."""
    col = coleccion_visitas(mongo.db, _frac_actual())
    if col is None:
        # Si esto truena es porque el login no guardó session["fraccionamiento"].
        raise RuntimeError(
            "No hay fraccionamiento en la sesión. "
            "Asegúrate de guardar session['fraccionamiento'] al hacer login."
        )
    return col


def _mi_residente_col():
    """Colección de residentes del fraccionamiento del residente logueado."""
    col = coleccion_residentes(mongo.db, _frac_actual())
    if col is None:
        raise RuntimeError(
            "No hay fraccionamiento en la sesión. "
            "Asegúrate de guardar session['fraccionamiento'] al hacer login."
        )
    return col


# =====================================================
# DASHBOARD RESIDENTE
# =====================================================


@resident_bp.route("/dashboard")
@login_required
@role_required("residente")
def dashboard():
    """Panel del residente con sus visitas recientes y estadísticas."""

    residente_id = session["user_id"]
    visitas_col = _mis_visitas()

    # =============================================
    # 5 VISITAS MÁS RECIENTES
    # =============================================

    visitas_recientes = list(
        visitas_col.find({"residente_id": residente_id}).sort("created_at", -1).limit(5)
    )

    # =============================================
    # ESTADISTICAS
    # =============================================

    total_visitas = visitas_col.count_documents({"residente_id": residente_id})

    visitas_dentro = visitas_col.count_documents(
        {"residente_id": residente_id, "estado": "dentro"}
    )

    visitas_finalizadas = visitas_col.count_documents(
        {"residente_id": residente_id, "estado": "salida_registrada"}
    )

    visitas_pendientes = visitas_col.count_documents(
        {
            "residente_id": residente_id,
            "estado": {"$in": ["activo", "pendiente_autorizacion"]},
        }
    )

    return render_template(
        "residente_dashboard.html",
        visitas_recientes=visitas_recientes,
        total_visitas=total_visitas,
        visitas_dentro=visitas_dentro,
        visitas_finalizadas=visitas_finalizadas,
        visitas_pendientes=visitas_pendientes,
    )


# =====================================================
# MIS VISITANTES
# =====================================================


@resident_bp.route("/visitantes")
@login_required
@role_required("residente")
def visitors():
    """Listado paginado de visitas del residente con filtros y búsqueda."""

    visitas_col = _mis_visitas()

    # =============================================
    # AUTO ABRIR QR
    # =============================================

    auto_qr = request.args.get("auto_qr")

    # =============================================
    # PAGINACION Y FILTROS
    # =============================================

    pagina = int(request.args.get("page", 1))

    por_pagina = 8

    fecha_inicio = request.args.get("fecha_inicio", "").strip()

    fecha_fin = request.args.get("fecha_fin", "").strip()

    busqueda = request.args.get("busqueda", "").strip()

    residente_id = session["user_id"]

    filtro = {"residente_id": residente_id}

    if fecha_inicio:

        filtro["fecha_visita"] = {"$gte": fecha_inicio}

    if fecha_fin:

        filtro.setdefault("fecha_visita", {})

        filtro["fecha_visita"]["$lte"] = fecha_fin

    if busqueda:

        filtro["$or"] = [
            {"nombre_visitante": {"$regex": busqueda, "$options": "i"}},
            {"telefono": {"$regex": busqueda, "$options": "i"}},
        ]

    # =============================================
    # CONSULTA
    # =============================================

    total_visitas = visitas_col.count_documents(filtro)

    total_paginas = max(1, (total_visitas + por_pagina - 1) // por_pagina)

    visitas = list(
        visitas_col.find(filtro)
        .sort("created_at", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    return render_template(
        "mis_visitantes.html",
        visitas=visitas,
        total_visitas=total_visitas,
        auto_qr=auto_qr,
        pagina=pagina,
        total_paginas=total_paginas,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        busqueda=busqueda,
    )


# =====================================================
# CANCELAR QR
# =====================================================


@resident_bp.route("/cancelar-qr/<token>", methods=["POST"])
@login_required
@role_required("residente")
def cancelar_qr(token):
    """Cancela el QR de una visita propia, si su estado aún lo permite."""

    visitas_col = _mis_visitas()

    visita = visitas_col.find_one(
        {"qr_token": token, "residente_id": session["user_id"]}
    )

    if not visita:
        return jsonify({"success": False, "message": "Visita no encontrada"}), 404

    # No permitir cancelar pases ya utilizados, finalizados o no vigentes
    if visita.get("estado") in [
        "pendiente_autorizacion",
        "dentro",
        "salida_registrada",
        "rechazado",
    ] or visita.get("qr_estado") in ["cancelado", "vencido", "rechazado"]:
        return (
            jsonify({"success": False, "message": "Este QR ya no puede cancelarse."}),
            409,
        )

    visitas_col.update_one(
        {"_id": visita["_id"]},
        {"$set": {"qr_estado": "cancelado", "estado": "cancelado"}},
    )
    socketio.emit("actualizar_dashboard", to="rol:admin")
    return {"success": True}


# =====================================================
# EDITAR VISITA
# =====================================================


@resident_bp.route("/editar-visita/<visita_id>", methods=["GET", "POST"])
@login_required
@role_required("residente")
def editar_visita(visita_id):
    """Edita una visita propia (temporal o recurrente) si aún es modificable."""

    visitas_col = _mis_visitas()

    visita = visitas_col.find_one(
        {"_id": ObjectId(visita_id), "residente_id": session["user_id"]}
    )

    if not visita:
        return redirect(url_for("resident.visitors"))

    # ==========================
    # BLOQUEAR VISITAS UTILIZADAS
    # ==========================

    if visita.get("estado") in [
        "pendiente_autorizacion",
        "dentro",
        "salida_registrada",
        "cancelado",
    ] or visita.get("qr_estado") in ["cancelado", "vencido"]:

        flash("Esta visita ya no puede modificarse.", "warning")

        return redirect(url_for("resident.visitors"))

    if request.method == "POST":

        # ==============================================
        # ACTUALIZAR SEGÚN MODALIDAD
        # ==============================================

        if visita.get("modalidad_visita") == "recurrente":

            dias_autorizados = request.form.getlist("dias[]")
            hora_desde = request.form.get("hora_desde")
            hora_hasta = request.form.get("hora_hasta")
            tipo_recurrente = request.form.get("tipo_recurrente")
            fecha_inicio_recurrente = request.form.get("fecha_inicio_recurrente")
            fecha_fin_recurrente = request.form.get("fecha_fin_recurrente")

            try:
                vigencia_desde = datetime.strptime(fecha_inicio_recurrente, "%Y-%m-%d")
            except (TypeError, ValueError):
                vigencia_desde = visita.get("vigencia_desde") or datetime.now()

            try:
                vigencia_hasta = datetime.strptime(fecha_fin_recurrente, "%Y-%m-%d")
            except (TypeError, ValueError):
                vigencia_hasta = visita.get("vigencia_hasta")

            visitas_col.update_one(
                {"_id": ObjectId(visita_id)},
                {
                    "$set": {
                        "telefono": request.form.get("telefono"),
                        "tipo_recurrente": tipo_recurrente,
                        "dias": dias_autorizados,
                        "dias_autorizados": dias_autorizados,
                        "hora_desde": hora_desde,
                        "hora_hasta": hora_hasta,
                        "hora_programada": hora_desde,
                        "fecha_inicio_recurrente": fecha_inicio_recurrente,
                        "fecha_fin_recurrente": fecha_fin_recurrente,
                        "vigencia_desde": vigencia_desde,
                        "vigencia_hasta": vigencia_hasta,
                    }
                },
            )

        else:

            visitas_col.update_one(
                {"_id": ObjectId(visita_id)},
                {
                    "$set": {
                        "telefono": request.form.get("telefono"),
                        "fecha_visita": request.form.get("fecha_visita"),
                        "hora_inicio": request.form.get("hora_inicio"),
                    }
                },
            )

        # ====================================
        # AVISAR A LOS DASHBOARDS (correcto)
        # ====================================

        socketio.emit("actualizar_dashboard", to="rol:admin")

        flash("Visita actualizada correctamente.", "success")

        return redirect(url_for("resident.visitors"))

    return render_template("editar_visita.html", visita=visita)


# =====================================================
# CREAR VISITA
# =====================================================


@resident_bp.route("/create-visit", methods=["GET", "POST"])
@login_required
@role_required("residente")
def create_visit():
    """Crea una visita temporal o recurrente y genera su token/QR de acceso."""

    # =============================================
    # OBTENER RESIDENTE (de la colección de su fraccionamiento)
    # =============================================

    residente = _mi_residente_col().find_one({"_id": ObjectId(session["user_id"])})

    # =============================================
    # POST
    # =============================================

    if request.method == "POST":

        modalidad = request.form.get("modalidad_visita", "temporal")

        # =============================================
        # GENERAR TOKEN Y QR
        # =============================================

        token = str(uuid.uuid4())

        qr_path = generate_qr(token)

        # =============================================
        # GUARDAR IMÁGENES
        # =============================================

        foto_visitante = guardar_imagen(
            request.files.get("foto_visitante"), "visitantes"
        )

        foto_placa = guardar_imagen(request.files.get("foto_placa"), "placas")

        # =============================================
        # VARIABLES BASE (siempre definidas)
        # =============================================

        vigencia_desde = None
        vigencia_hasta = None

        dias_autorizados = []

        # Campos recurrentes (nombres reales del formulario)
        tipo_recurrente = None
        hora_desde = None
        hora_hasta = None
        fecha_inicio_recurrente = None
        fecha_fin_recurrente = None

        # Compatibilidad con validación / código anterior
        hora_programada = None
        hora_limite_salida = None

        fecha_visita = request.form.get("fecha_visita")

        hora_inicio = request.form.get("hora_inicio")

        # =============================================
        # VISITA RECURRENTE
        # =============================================

        if modalidad == "recurrente":

            # =========================================
            # DATOS REALES DEL FORMULARIO
            # =========================================

            tipo_recurrente = request.form.get("tipo_recurrente")

            dias_autorizados = request.form.getlist("dias[]")

            hora_desde = request.form.get("hora_desde")

            hora_hasta = request.form.get("hora_hasta")

            fecha_inicio_recurrente = request.form.get("fecha_inicio_recurrente")

            fecha_fin_recurrente = request.form.get("fecha_fin_recurrente")

            # =========================================
            # VIGENCIA REAL (según lo que eligió el residente)
            # Se guardan como datetime para la validación del QR.
            # =========================================

            try:
                vigencia_desde = datetime.strptime(fecha_inicio_recurrente, "%Y-%m-%d")
            except (TypeError, ValueError):
                vigencia_desde = datetime.now()

            try:
                vigencia_hasta = datetime.strptime(fecha_fin_recurrente, "%Y-%m-%d")
            except (TypeError, ValueError):
                vigencia_hasta = vigencia_desde + timedelta(days=30)

            # =========================================
            # COMPATIBILIDAD
            # =========================================

            hora_programada = hora_desde
            hora_inicio = hora_desde

            # =========================================
            # FECHA BASE: el primer día válido del rango
            # =========================================

            fecha_visita = fecha_inicio_recurrente or vigencia_desde.strftime(
                "%Y-%m-%d"
            )

        # =============================================
        # CREAR OBJETO VISITA
        # =============================================

        visita = {
            "residente_id": session["user_id"],
            "residente_nombre": session["nombre"],
            "telefono_residente": residente.get("telefono", ""),
            "nombre_visitante": request.form["nombre_visitante"].strip(),
            "foto_visitante": foto_visitante,
            "foto_placa": foto_placa,
            "telefono": request.form["telefono"].strip(),
            "modalidad_visita": modalidad,
            "motivo": request.form["motivo"].strip(),
            "fraccionamiento": residente["fraccionamiento"],
            "condominio": residente["privada"],
            "residencia_destino": residente["numero_casa"],
            "fecha_visita": fecha_visita,
            "hora_inicio": hora_inicio,
            # ---- Campos recurrentes (los que lee el dashboard) ----
            "tipo_recurrente": tipo_recurrente,
            "dias": dias_autorizados,
            "dias_autorizados": dias_autorizados,
            "hora_desde": hora_desde,
            "hora_hasta": hora_hasta,
            "fecha_inicio_recurrente": fecha_inicio_recurrente,
            "fecha_fin_recurrente": fecha_fin_recurrente,
            # ---- Compatibilidad / validación ----
            "hora_programada": hora_programada,
            "hora_limite_salida": hora_limite_salida,
            "vigencia_desde": vigencia_desde,
            "vigencia_hasta": vigencia_hasta,
            # ---- Estado de salida ----
            "hora_salida": None,
            "fecha_salida": None,
            "entrada_consumida": False,
            "vehiculo": {
                "tiene_vehiculo": True,
                "placa": request.form.get("placa", "").strip(),
                "marca": request.form.get("marca", "").strip(),
                "modelo": request.form.get("modelo", "").strip(),
                "color": request.form.get("color", "").strip(),
            },
            "qr_token": token,
            "qr_path": qr_path,
            "qr_estado": "activo",
            "estado": "activo",
            "created_at": datetime.now(),
        }

        # =============================================
        # GUARDAR EN MONGO (colección de visitas del fraccionamiento)
        # =============================================

        _mis_visitas().insert_one(visita)

        # =============================================
        # SOCKET NUEVA VISITA
        # =============================================

        datos_visita = {
            "mensaje": "Nueva visita registrada",
            "visitante": visita["nombre_visitante"],
            "residente": visita["residente_nombre"],
        }
        socketio.emit("nueva_visita", datos_visita, to="rol:admin")
        socketio.emit("nueva_visita", datos_visita, to="rol:guardia")

        # =============================================
        # REDIRECCIONAR Y ABRIR QR AUTOMÁTICAMENTE
        # =============================================

        return redirect(url_for("resident.visitors", auto_qr=token))

    # =============================================
    # RENDER GET
    # =============================================

    return render_template("crear_visita.html", residente=residente)
