from flask import Blueprint, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import uuid

from bson.objectid import ObjectId

from extensions import mongo, socketio

from utils.auth import login_required, role_required
from utils.qr_generator import generate_qr
from utils.uploads import guardar_imagen
from utils.visita_validacion import vigencia_recurrente_meses

resident_bp = Blueprint("resident", __name__, url_prefix="/resident")


# =====================================================
# DASHBOARD RESIDENTE
# =====================================================


@resident_bp.route("/dashboard")
@login_required
@role_required("residente")
def dashboard():

    residente_id = session["user_id"]

    # =============================================
    # 5 VISITAS MÁS RECIENTES
    # =============================================

    visitas_recientes = list(
        mongo.db.visits.find({"residente_id": residente_id})
        .sort("created_at", -1)
        .limit(5)
    )

    # =============================================
    # ESTADISTICAS
    # =============================================

    total_visitas = mongo.db.visits.count_documents(
        {"residente_id": residente_id}
    )

    visitas_dentro = mongo.db.visits.count_documents(
        {"residente_id": residente_id, "estado": "dentro"}
    )

    visitas_finalizadas = mongo.db.visits.count_documents(
        {"residente_id": residente_id, "estado": "salida_registrada"}
    )

    visitas_pendientes = mongo.db.visits.count_documents(
        {"residente_id": residente_id, "estado": "activo"}
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

        filtro["nombre_visitante"] = {"$regex": busqueda, "$options": "i"}

    # =============================================
    # CONSULTA
    # =============================================

    total_visitas = mongo.db.visits.count_documents(filtro)

    total_paginas = max(1, (total_visitas + por_pagina - 1) // por_pagina)

    visitas = list(
        mongo.db.visits.find(filtro)
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

    mongo.db.visits.update_one(
        {"qr_token": token, "residente_id": session["user_id"]},
        {"$set": {"qr_estado": "cancelado", "estado": "cancelado"}},
    )

    return {"success": True}


# =====================================================
# CREAR VISITA
# =====================================================


@resident_bp.route("/create-visit", methods=["GET", "POST"])
@login_required
@role_required("residente")
def create_visit():

    # =============================================
    # OBTENER RESIDENTE
    # =============================================

    residente = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})

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
        # VARIABLES
        # =============================================

        vigencia_desde = None
        vigencia_hasta = None

        dias_autorizados = []

        hora_programada = None

        hora_limite_salida = None

        fecha_visita = request.form.get("fecha_visita")

        hora_inicio = request.form.get("hora_inicio")

        # =============================================
        # VISITA RECURRENTE
        # =============================================

        if modalidad == "recurrente":

            # =========================================
            # DATOS DEL FORMULARIO
            # =========================================

            dias_autorizados = request.form.getlist("dias[]")

            hora_programada = request.form.get("hora_programada")

            hora_limite_salida = request.form.get("hora_salida")

            vigencia_qr = request.form.get("vigencia_qr")

            hora_inicio = hora_programada

            # =========================================
            # FECHA ACTUAL
            # =========================================

            vigencia_desde = datetime.now()

            # =========================================
            # CALCULAR VIGENCIA
            # =========================================

            if vigencia_qr == "1_semana":

                vigencia_hasta = vigencia_desde + timedelta(days=7)

            elif vigencia_qr == "15_dias":

                vigencia_hasta = vigencia_desde + timedelta(days=15)

            elif vigencia_qr == "1_mes":

                vigencia_hasta = vigencia_desde + timedelta(days=30)

            elif vigencia_qr == "3_meses":

                vigencia_hasta = vigencia_desde + timedelta(days=90)

            else:

                vigencia_hasta = vigencia_desde + timedelta(days=30)

            # =========================================
            # FECHA BASE
            # =========================================

            fecha_visita = vigencia_desde.strftime("%Y-%m-%d")

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
            "dias_autorizados": dias_autorizados,
            "hora_programada": hora_programada,
            "hora_limite_salida": hora_limite_salida,
            "vigencia_desde": vigencia_desde,
            "vigencia_hasta": vigencia_hasta,
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
        # GUARDAR EN MONGO
        # =============================================

        mongo.db.visits.insert_one(visita)

        # =============================================
        # SOCKET NUEVA VISITA
        # =============================================

        socketio.emit(
            "nueva_visita",
            {
                "mensaje": "Nueva visita registrada",
                "visitante": visita["nombre_visitante"],
                "residente": visita["residente_nombre"],
            },
        )

        # =============================================
        # REDIRECCIONAR Y ABRIR QR AUTOMÁTICAMENTE
        # =============================================

        return redirect(url_for("resident.visitors", auto_qr=token))

    # =============================================
    # RENDER GET
    # =============================================

    return render_template("crear_visita.html", residente=residente)
