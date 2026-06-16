# =========================================================
# IMPORTACIONES
# =========================================================

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
)

from extensions import mongo, socketio
from utils.auth import login_required, role_required

from bson.objectid import ObjectId

from io import BytesIO
from datetime import datetime, timedelta
import os
from werkzeug.security import generate_password_hash

# =========================================================
# IMPORT EXCEL
# =========================================================

import pandas as pd

# =========================================================
# REPORTLAB PDF
# =========================================================

from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)

from reportlab.platypus.flowables import HRFlowable

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

# =========================================================
# BLUEPRINT
# =========================================================

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# =========================================================
# HELPER: METADATA PDF (reutilizable en todos los reportes)
# =========================================================


def _pdf_metadata(titulo, asunto):
    """Devuelve una función onPage que escribe la metadata del PDF."""

    def _aplicar(canvas, doc):
        canvas.setTitle(f"Acceso QR | {titulo}")
        canvas.setAuthor("Acceso QR")
        canvas.setSubject(asunto)
        canvas.setCreator("Acceso QR | Sistema Residencial")

    return _aplicar


def _registrar_historial_reporte(nombre, tipo, formato):
    """Guarda un registro cada vez que se exporta un reporte."""
    from flask import session

    mongo.db.reportes.insert_one(
        {
            "nombre": nombre,
            "tipo": tipo,
            "formato": formato,
            "usuario": session.get("nombre", "Administrador"),
            "fecha": datetime.now(),
            "estado": "Generado",
        }
    )


# =========================================================
# DASHBOARD ADMIN
# =========================================================

@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():
 
    import re
    from datetime import datetime as _dt
 
    MESES_ES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
 
    modo = request.args.get("modo", "dia")
    busqueda = request.args.get("busqueda", "").strip()
    fecha_inicio_tabla = request.args.get("fecha_inicio_tabla", "").strip()
    fecha_fin_tabla = request.args.get("fecha_fin_tabla", "").strip()
 
    hoy = datetime.now()
    dia_sel = request.args.get("dia", "").strip()
    semana_sel = request.args.get("semana", "").strip()
    mes_sel = request.args.get("mes", "").strip()
 
    # -----------------------------------------------------
    # 1) RANGO DEL PERÍODO (según el modo de arriba)
    # -----------------------------------------------------
    if modo == "semana":
        if not semana_sel:
            iso = hoy.isocalendar()
            semana_sel = f"{iso[0]}-W{iso[1]:02d}"
        anio, sem = semana_sel.split("-W")
        ini = _dt.strptime(f"{anio}-W{int(sem):02d}-1", "%G-W%V-%u")
        fin = ini + timedelta(days=6)
        periodo_inicio_str = ini.strftime("%Y-%m-%d")
        periodo_fin_str = fin.strftime("%Y-%m-%d")
        label_periodo = f"Semana del {ini.strftime('%d/%m/%Y')} al {fin.strftime('%d/%m/%Y')}"
        periodo_qs = f"modo=semana&semana={semana_sel}"
 
    elif modo == "mes":
        if not mes_sel:
            mes_sel = hoy.strftime("%Y-%m")
        anio, mes = map(int, mes_sel.split("-"))
        ini = datetime(anio, mes, 1)
        fin_excl = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
        fin = fin_excl - timedelta(days=1)
        periodo_inicio_str = ini.strftime("%Y-%m-%d")
        periodo_fin_str = fin.strftime("%Y-%m-%d")
        label_periodo = f"{MESES_ES[mes]} {anio}"
        periodo_qs = f"modo=mes&mes={mes_sel}"
 
    else:
        modo = "dia"
        if not dia_sel:
            dia_sel = hoy.strftime("%Y-%m-%d")
        periodo_inicio_str = dia_sel
        periodo_fin_str = dia_sel
        d = _dt.strptime(dia_sel, "%Y-%m-%d")
        label_periodo = f"{d.day} de {MESES_ES[d.month]} {d.year}"
        periodo_qs = f"modo=dia&dia={dia_sel}"
 
    # -----------------------------------------------------
    # 2) RANGO EFECTIVO (sincronización)
    #    Si el usuario puso fechas en la tabla, esas mandan; si no, = período.
    # -----------------------------------------------------
    override = bool(fecha_inicio_tabla or fecha_fin_tabla)
 
    inicio_str = fecha_inicio_tabla or periodo_inicio_str
    fin_str = fecha_fin_tabla or periodo_fin_str
 
    # que inicio <= fin
    if inicio_str > fin_str:
        inicio_str, fin_str = fin_str, inicio_str
 
 
    inicio_dt = _dt.strptime(inicio_str, "%Y-%m-%d")
    fin_dt = _dt.strptime(fin_str, "%Y-%m-%d") + timedelta(days=1)
    dias_periodo = max(1, (fin_dt - inicio_dt).days)
 
    if override:
        rango_label = (
            f"Del {inicio_dt.strftime('%d/%m/%Y')} "
            f"al {(fin_dt - timedelta(days=1)).strftime('%d/%m/%Y')}"
        )
    else:
        rango_label = label_periodo
 
    # -----------------------------------------------------
    # FILTROS BASE (+ búsqueda)
    # -----------------------------------------------------
    busqueda_visitas = None
    if busqueda:
        rx = {"$regex": re.escape(busqueda), "$options": "i"}
        busqueda_visitas = [{"nombre_visitante": rx}, {"residente_nombre": rx}]
 
    match_visitas = {"fecha_visita": {"$gte": inicio_str, "$lte": fin_str}}
    if busqueda_visitas:
        match_visitas["$or"] = busqueda_visitas
 
    match_accesos = {"fecha_hora": {"$gte": inicio_dt, "$lt": fin_dt}}
    match_incidencias = {"fecha_hora": {"$gte": inicio_dt, "$lt": fin_dt}}
    if busqueda:
        rx = {"$regex": re.escape(busqueda), "$options": "i"}
        match_accesos["$or"] = [{"visitante": rx}, {"guardia_nombre": rx}, {"accion": rx}]
        match_incidencias["$or"] = [{"visitante": rx}, {"guardia_nombre": rx}, {"descripcion": rx}]
 
    visits = mongo.db.visits
    logs = mongo.db.access_logs
    incs = mongo.db.incidencias
 
    # -----------------------------------------------------
    # KPIs de visitas
    # -----------------------------------------------------
    estado_counts = {
        row["_id"]: row["n"]
        for row in visits.aggregate([
            {"$match": match_visitas},
            {"$group": {"_id": "$estado", "n": {"$sum": 1}}},
        ])
    }
    total_visitas = sum(estado_counts.values())
    dentro = estado_counts.get("dentro", 0)
    activas = estado_counts.get("activo", 0)
    salidas = estado_counts.get("salida_registrada", 0)
    pendientes_autorizacion = estado_counts.get("pendiente_autorizacion", 0)
 
    total_residentes = mongo.db.users.count_documents({"rol": "residente"})
    total_guardias = mongo.db.users.count_documents({"rol": "guardia"})
    total_incidencias = incs.count_documents(match_incidencias)
    rechazados = logs.count_documents({**match_accesos, "resultado": "rechazado"})
 
    # -----------------------------------------------------
    # TIPOS DE VISITA
    # -----------------------------------------------------
    tipo_labels, tipo_data = [], []
    for row in visits.aggregate([
        {"$match": match_visitas},
        {"$group": {"_id": {"$ifNull": ["$modalidad_visita", "General"]}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]):
        tipo_labels.append(row["_id"] or "General")
        tipo_data.append(row["n"])
 
    # -----------------------------------------------------
    # VISITAS POR DÍA
    # -----------------------------------------------------
    dias_raw = {
        row["_id"]: row["n"]
        for row in visits.aggregate([
            {"$match": match_visitas},
            {"$group": {"_id": "$fecha_visita", "n": {"$sum": 1}}},
        ])
        if row["_id"]
    }
    fechas_ordenadas = sorted(dias_raw.keys(), key=lambda x: _dt.strptime(x, "%Y-%m-%d"))
    dias_labels = [_dt.strptime(f, "%Y-%m-%d").strftime("%d/%m") for f in fechas_ordenadas]
    dias_data = [dias_raw[f] for f in fechas_ordenadas]
 
    # -----------------------------------------------------
    # TOP / ACTIVOS RESIDENTES
    # -----------------------------------------------------
    residentes_rank = [
        (row["_id"] or "Sin residente", row["n"])
        for row in visits.aggregate([
            {"$match": match_visitas},
            {"$group": {"_id": "$residente_nombre", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 10},
        ])
    ]
    top_residentes = residentes_rank[:5]
    residentes_activos = residentes_rank
 
    # -----------------------------------------------------
    # PRIVADAS
    # -----------------------------------------------------
    privadas_labels, privadas_data = [], []
    for row in visits.aggregate([
        {"$match": match_visitas},
        {"$group": {"_id": {"$ifNull": ["$condominio", "General"]}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]):
        privadas_labels.append(row["_id"] or "General")
        privadas_data.append(row["n"])
 
    # -----------------------------------------------------
    # HORAS PICO (accesos)
    # -----------------------------------------------------
    horas_raw = {
        row["_id"]: row["n"]
        for row in logs.aggregate([
            {"$match": match_accesos},
            {"$group": {"_id": {"$hour": "$fecha_hora"}, "n": {"$sum": 1}}},
        ])
        if row["_id"] is not None
    }
    horas_labels = [_dt.strptime(f"{h:02d}", "%H").strftime("%I %p") for h in sorted(horas_raw)]
    horas_data = [horas_raw[h] for h in sorted(horas_raw)]
 
    # -----------------------------------------------------
    # TOP GUARDIAS
    # -----------------------------------------------------
    top_guardias = [
        (row["_id"] or "Desconocido", row["n"])
        for row in logs.aggregate([
            {"$match": match_accesos},
            {"$group": {"_id": "$guardia_nombre", "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
            {"$limit": 5},
        ])
    ]
 
    # -----------------------------------------------------
    # LISTAS CORTAS
    # -----------------------------------------------------
    actividad_reciente = list(logs.find(match_accesos).sort("fecha_hora", -1).limit(5))
    accesos_rechazados = list(
        logs.find({**match_accesos, "resultado": "rechazado"})
        .sort("fecha_hora", -1).limit(10)
    )
    visitas_dentro = list(
        visits.find({**match_visitas, "estado": "dentro"})
        .sort("fecha_visita", -1).limit(50)
    )
    vehiculos = visits.distinct("vehiculo.placa", match_visitas)
 
    # -----------------------------------------------------
    # TABLA (mismo rango que todo lo demás)
    # -----------------------------------------------------
    pagina_tabla = int(request.args.get("page", 1))
    por_pagina_tabla = 5
    total_visitas_tabla = visits.count_documents(match_visitas)
    total_paginas_tabla = max(1, (total_visitas_tabla + por_pagina_tabla - 1) // por_pagina_tabla)
    visitas_tabla_paginada = list(
        visits.find(match_visitas)
        .sort([("fecha_visita", -1), ("created_at", -1)])
        .skip((pagina_tabla - 1) * por_pagina_tabla)
        .limit(por_pagina_tabla)
    )
 
    # -----------------------------------------------------
    # ALERTAS / PROMEDIO
    # -----------------------------------------------------
    alertas = []
    if rechazados >= 5:
        alertas.append("Demasiados QR rechazados")
    if dentro >= 20:
        alertas.append("Muchas personas dentro")
 
    promedio = total_visitas if dias_periodo <= 1 else round(total_visitas / dias_periodo, 2)
 
    incidencias_preview = list(incs.find(match_incidencias).sort("fecha_hora", -1).limit(50))
 
    return render_template(
        "admin_dashboard.html",
        modo=modo,
        filtro=modo,
        dia_sel=dia_sel,
        semana_sel=semana_sel,
        mes_sel=mes_sel,
        rango_label=rango_label,
        periodo_qs=periodo_qs,
        visitas=visitas_tabla_paginada,
        accesos=actividad_reciente,
        incidencias=incidencias_preview,
        total_visitas=total_visitas,
        dentro=dentro,
        activas=activas,
        salidas=salidas,
        total_residentes=total_residentes,
        total_guardias=total_guardias,
        total_incidencias=total_incidencias,
        rechazados=rechazados,
        tipo_labels=tipo_labels,
        tipo_data=tipo_data,
        dias_labels=dias_labels,
        dias_data=dias_data,
        top_residentes=top_residentes,
        actividad_reciente=actividad_reciente,
        horas_labels=horas_labels,
        horas_data=horas_data,
        privadas_labels=privadas_labels,
        privadas_data=privadas_data,
        visitas_dentro=visitas_dentro,
        alertas=alertas,
        accesos_rechazados=accesos_rechazados,
        top_guardias=top_guardias,
        residentes_activos=residentes_activos,
        vehiculos=vehiculos,
        promedio=promedio,
        busqueda=busqueda,
        visitas_tabla=visitas_tabla_paginada,
        fecha_inicio_tabla=fecha_inicio_tabla,
        fecha_fin_tabla=fecha_fin_tabla,
        pagina_tabla=pagina_tabla,
        total_paginas_tabla=total_paginas_tabla,
        pendientes_autorizacion=pendientes_autorizacion,
    )
# =====================================================
# GESTIÓN DE RESIDENTES
# =====================================================


@admin_bp.route("/residentes")
@login_required
@role_required("admin")
def residentes():

    pagina = int(request.args.get("page", 1))
    por_pagina = 10
    total = mongo.db.users.count_documents({"rol": "residente"})
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    usuarios = list(
        mongo.db.users.find({"rol": "residente"})
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    return render_template(
        "admin_residentes.html",
        usuarios=usuarios,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# =========================================
# REGISTRAR RESIDENTE
# =========================================


@admin_bp.route("/residentes/registrar", methods=["GET", "POST"])
@login_required
@role_required("admin")
def registrar_residente():

    if request.method == "POST":

        # =================================================
        # OBTENER DATOS Y NORMALIZAR
        # =================================================

        nombre = request.form["nombre"].strip()

        correo = request.form["correo"].strip().lower()

        telefono = request.form["telefono"].strip()

        fraccionamiento = request.form["fraccionamiento"].strip().lower()

        privada = request.form["privada"].strip().lower()

        numero_casa = request.form["numero_casa"].strip().lower()

        # =================================================
        # VALIDAR CORREO DUPLICADO
        # =================================================

        correo_existente = mongo.db.users.find_one({"correo": correo})

        if correo_existente:

            flash("El correo electrónico ya se encuentra registrado.", "danger")

            return redirect(url_for("admin.registrar_residente"))

        # =================================================
        # VALIDAR CASA DUPLICADA
        # NO PERMITIR MISMA CASA EN
        # MISMO FRACCIONAMIENTO Y PRIVADA
        # =================================================

        casa_existente = mongo.db.users.find_one(
            {
                "rol": "residente",
                "fraccionamiento": fraccionamiento,
                "privada": privada,
                "numero_casa": numero_casa,
            }
        )

        # =================================================
        # SI YA EXISTE LA CASA
        # =================================================

        if casa_existente:

            print("DUPLICADO DETECTADO")

            flash(
                f"La casa {numero_casa.upper()} ya está registrada en "
                f"{privada.title()} - {fraccionamiento.title()}",
                "danger",
            )

            return redirect(url_for("admin.registrar_residente"))

        # =================================================
        # CREAR RESIDENTE
        # =================================================

        nuevo = {
            "nombre": nombre,
            "correo": correo,
            "password": generate_password_hash("Residente123*"),
            "telefono": telefono,
            "fraccionamiento": fraccionamiento,
            "privada": privada,
            "numero_casa": numero_casa,
            "estado": "activo",
            "rol": "residente",
            "created_at": datetime.now(),
            "ultimo_acceso": None,
            "intentos_fallidos": 0,
            "bloqueado_hasta": None,
        }

        # =================================================
        # INSERTAR USUARIO
        # =================================================

        print("NO EXISTE DUPLICADO")

        mongo.db.users.insert_one(nuevo)

        socketio.emit("actualizar_residentes", to="rol:admin")

        socketio.emit("actualizar_dashboard", to="rol:admin")

        # =================================================
        # MENSAJE
        # =================================================

        flash("Residente registrado correctamente.", "success")

        return redirect(url_for("admin.residentes"))

    # =====================================================
    # FORMULARIO
    # =====================================================

    return render_template("registrar_residente.html")


# =========================================
# VER PERFIL RESIDENTE
# =========================================


@admin_bp.route("/residentes/<id>")
@login_required
@role_required("admin")
def ver_residente(id):

    usuario = mongo.db.users.find_one({"_id": ObjectId(id)})

    return render_template("ver_residente.html", usuario=usuario)


# =========================================
# EDITAR RESIDENTE
# =========================================


@admin_bp.route("/residentes/editar/<id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def editar_residente(id):

    usuario = mongo.db.users.find_one({"_id": ObjectId(id)})

    if request.method == "POST":

        mongo.db.users.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "nombre": request.form["nombre"],
                    "correo": request.form["correo"],
                    "telefono": request.form["telefono"],
                    "fraccionamiento": request.form["fraccionamiento"],
                    "privada": request.form["privada"],
                    "numero_casa": request.form["numero_casa"],
                }
            },
        )

        socketio.emit("actualizar_residentes", to="rol:admin")

        socketio.emit("actualizar_dashboard", to="rol:admin")

        flash("Residente actualizado correctamente")

        return redirect(url_for("admin.residentes"))

    return render_template("editar_residente.html", usuario=usuario)


# =========================================
# BLOQUEAR RESIDENTE
# =========================================


@admin_bp.route("/residentes/bloquear/<id>")
@login_required
@role_required("admin")
def bloquear_residente(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "inactivo"}})

    socketio.emit("actualizar_residentes", to="rol:admin")

    socketio.emit("actualizar_dashboard", to="rol:admin")

    flash("Residente bloqueado correctamente")

    return redirect(url_for("admin.residentes"))


# =========================================
# ELIMINAR RESIDENTE
# =========================================


@admin_bp.route("/residentes/eliminar/<id>")
@login_required
@role_required("admin")
def eliminar_residente(id):

    mongo.db.users.delete_one({"_id": ObjectId(id)})

    socketio.emit("actualizar_residentes", to="rol:admin")

    socketio.emit("actualizar_dashboard", to="rol:admin")

    flash("Residente eliminado correctamente.", "success")

    return redirect(url_for("admin.residentes"))


# =====================================================
# DESBLOQUEAR RESIDENTE
# =====================================================


@admin_bp.route("/desbloquear_residente/<id>")
@login_required
@role_required("admin")
def desbloquear_residente(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "activo"}})

    socketio.emit("actualizar_residentes", to="rol:admin")

    flash("Residente desbloqueado correctamente", "success")

    return redirect(url_for("admin.residentes"))


# =========================================
# EXPORTAR RESIDENTES PDF
# =========================================


@admin_bp.route("/residentes/pdf")
@login_required
@role_required("admin")
def exportar_residentes_pdf():

    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.styles import ParagraphStyle

    usuarios = list(mongo.db.users.find({"rol": "residente"}))

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elementos = []

    styles = getSampleStyleSheet()

    estilo_normal = ParagraphStyle(
        "normal",
        fontSize=8,
        leading=10,
    )

    titulo = Paragraph(
        "<font size=22><b>Reporte de Residentes</b></font>",
        styles["Title"],
    )

    elementos.append(titulo)

    elementos.append(Spacer(1, 15))

    data = [
        [
            "Nombre",
            "Correo",
            "Teléfono",
            "Privada",
            "Casa",
            "Estado",
        ]
    ]

    for usuario in usuarios:

        data.append(
            [
                Paragraph(usuario.get("nombre", ""), estilo_normal),
                Paragraph(usuario.get("correo", ""), estilo_normal),
                Paragraph(usuario.get("telefono", ""), estilo_normal),
                Paragraph(usuario.get("privada", ""), estilo_normal),
                Paragraph(usuario.get("numero_casa", ""), estilo_normal),
                Paragraph(usuario.get("estado", ""), estilo_normal),
            ]
        )

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[170, 250, 120, 100, 70, 90],
    )

    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    metadata = _pdf_metadata("Reporte de Residentes", "Reporte de Residentes")

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Residentes_{datetime.now().strftime('%d%m%Y')}.pdf",
        "Residentes",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Residentes_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# GESTIÓN DE GUARDIAS
# =========================================================


@admin_bp.route("/guardias")
@login_required
@role_required("admin")
def guardias():

    pagina = int(request.args.get("page", 1))
    por_pagina = 10
    total = mongo.db.users.count_documents({"rol": "guardia"})
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    guardias = list(
        mongo.db.users.find({"rol": "guardia"})
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    return render_template(
        "admin_guardias.html",
        guardias=guardias,
        pagina=pagina,
        total_paginas=total_paginas,
    )


@admin_bp.route("/guardias/registrar", methods=["GET", "POST"])
@login_required
@role_required("admin")
def registrar_guardia():

    if request.method == "POST":

        # =========================================
        # DATOS FORMULARIO
        # =========================================

        nombre = request.form["nombre"].strip()

        correo = request.form["correo"].strip()

        telefono = request.form["telefono"].strip()

        turno = request.form["turno"].strip()

        estado = request.form["estado"].strip()

        # =========================================
        # CONTRASEÑA POR DEFECTO
        # =========================================

        password_default = "Guardia123*"

        # =========================================
        # VALIDAR CORREO DUPLICADO
        # =========================================

        existe = mongo.db.users.find_one({"correo": correo})

        if existe:

            flash(
                "Ese correo ya se encuentra registrado.",
                "danger",
            )

            return redirect(url_for("admin.registrar_guardia"))

        # =========================================
        # CREAR GUARDIA
        # =========================================

        nuevo = {
            "nombre": nombre,
            "correo": correo,
            "password": generate_password_hash(password_default),
            "telefono": telefono,
            "turno": turno,
            "estado": estado,
            "rol": "guardia",
            "created_at": datetime.now(),
            "ultimo_acceso": None,
            "intentos_fallidos": 0,
            "bloqueado_hasta": None,
        }

        # =========================================
        # INSERTAR
        # =========================================

        mongo.db.users.insert_one(nuevo)

        socketio.emit("actualizar_guardias", to="rol:admin")

        socketio.emit("actualizar_dashboard", to="rol:admin")

        # =========================================
        # MENSAJE
        # =========================================

        flash(
            f"Guardia registrado correctamente. "
            f"Contraseña temporal: {password_default}",
            "success",
        )

        return redirect(url_for("admin.guardias"))

    return render_template("registrar_guardia.html")


@admin_bp.route("/guardias/<id>")
@login_required
@role_required("admin")
def ver_guardia(id):

    guardia = mongo.db.users.find_one({"_id": ObjectId(id)})

    return render_template("ver_guardia.html", guardia=guardia)


@admin_bp.route("/guardias/editar/<id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def editar_guardia(id):

    guardia = mongo.db.users.find_one({"_id": ObjectId(id)})

    if request.method == "POST":

        mongo.db.users.update_one(
            {"_id": ObjectId(id)},
            {
                "$set": {
                    "nombre": request.form["nombre"],
                    "correo": request.form["correo"],
                    "telefono": request.form["telefono"],
                    "turno": request.form["turno"],
                    "estado": request.form["estado"],
                }
            },
        )

        socketio.emit("actualizar_guardias", to="rol:admin")

        socketio.emit("actualizar_dashboard", to="rol:admin")

        flash("Guardia actualizado correctamente")

        return redirect(url_for("admin.guardias"))

    return render_template("editar_guardia.html", guardia=guardia)


@admin_bp.route("/guardias/desactivar/<id>")
@login_required
@role_required("admin")
def desactivar_guardia(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "inactivo"}})

    socketio.emit("actualizar_guardias", to="rol:admin")

    socketio.emit("actualizar_dashboard", to="rol:admin")

    flash("Guardia desactivado correctamente")

    return redirect(url_for("admin.guardias"))


@admin_bp.route("/guardias/activar/<id>")
@login_required
@role_required("admin")
def activar_guardia(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "activo"}})

    socketio.emit("actualizar_guardias", to="rol:admin")

    socketio.emit("actualizar_dashboard", to="rol:admin")

    flash("Guardia activado correctamente")

    return redirect(url_for("admin.guardias"))


# =========================================
# EXPORTAR GUARDIAS PDF
# =========================================
@admin_bp.route("/guardias/pdf")
@login_required
@role_required("admin")
def exportar_guardias_pdf():

    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.styles import ParagraphStyle

    guardias = list(mongo.db.users.find({"rol": "guardia"}))

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elementos = []

    styles = getSampleStyleSheet()

    estilo_normal = ParagraphStyle(
        "normal",
        fontSize=8,
        leading=10,
    )

    titulo = Paragraph(
        "<font size=22><b>Reporte de Guardias</b></font>",
        styles["Title"],
    )

    elementos.append(titulo)

    elementos.append(Spacer(1, 20))

    data = [
        [
            "Nombre",
            "Correo",
            "Teléfono",
            "Turno",
            "Estado",
        ]
    ]

    for guardia in guardias:

        data.append(
            [
                Paragraph(guardia.get("nombre", ""), estilo_normal),
                Paragraph(guardia.get("correo", ""), estilo_normal),
                Paragraph(guardia.get("telefono", ""), estilo_normal),
                Paragraph(guardia.get("turno", ""), estilo_normal),
                Paragraph(guardia.get("estado", ""), estilo_normal),
            ]
        )

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[180, 250, 130, 100, 100],
    )

    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    metadata = _pdf_metadata("Reporte de Guardias", "Reporte de Guardias")

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Guardias_{datetime.now().strftime('%d%m%Y')}.pdf",
        "Guardias",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Guardias_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# HISTORIAL DE ACCESOS
# =========================================================


@admin_bp.route("/accesos")
@login_required
@role_required("admin")
def accesos():

    pagina = int(request.args.get("page", 1))
    por_pagina = 15
    total = mongo.db.access_logs.count_documents({})
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    accesos = list(
        mongo.db.access_logs.find()
        .sort("fecha_hora", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    return render_template(
        "admin_accesos.html",
        accesos=accesos,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# =========================================================
# EXPORTAR ACCESOS PDF
# =========================================================
@admin_bp.route("/accesos/pdf")
@login_required
@role_required("admin")
def exportar_accesos_pdf():

    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.styles import ParagraphStyle

    accesos = list(mongo.db.access_logs.find().sort("fecha_hora", -1))

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elementos = []

    styles = getSampleStyleSheet()

    estilo_normal = ParagraphStyle(
        "normal",
        fontSize=8,
        leading=10,
    )

    titulo = Paragraph(
        "<font size=22><b>Reporte de Accesos</b></font>",
        styles["Title"],
    )

    elementos.append(titulo)

    elementos.append(Spacer(1, 15))

    data = [
        [
            "Guardia",
            "Acción",
            "Resultado",
            "Fecha",
        ]
    ]

    for acceso in accesos:

        fecha = acceso.get("fecha_hora")

        if fecha:
            fecha = fecha.strftime("%d/%m/%Y %I:%M %p")

        data.append(
            [
                Paragraph(acceso.get("guardia_nombre", ""), estilo_normal),
                Paragraph(acceso.get("accion", ""), estilo_normal),
                Paragraph(acceso.get("resultado", ""), estilo_normal),
                Paragraph(str(fecha), estilo_normal),
            ]
        )

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[180, 220, 220, 140],
    )

    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    metadata = _pdf_metadata("Reporte de Accesos", "Reporte de Accesos")

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Accesos_{datetime.now().strftime('%d%m%Y')}.pdf",
        "Accesos",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Accesos_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# EXPORTAR ACCESOS EXCEL
# =========================================================
@admin_bp.route("/accesos/excel")
@login_required
@role_required("admin")
def exportar_accesos_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    accesos = list(mongo.db.access_logs.find().sort("fecha_hora", -1))

    data = []

    for acceso in accesos:

        fecha = acceso.get("fecha_hora")

        if fecha:
            fecha = fecha.strftime("%d/%m/%Y %I:%M %p")

        data.append(
            {
                "Guardia": acceso.get("guardia_nombre", ""),
                "Acción": acceso.get("accion", ""),
                "Resultado": acceso.get("resultado", ""),
                "Fecha": fecha,
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Accesos", index=False)

        worksheet = writer.sheets["Accesos"]

        header_fill = PatternFill(
            start_color="0F172A",
            end_color="0F172A",
            fill_type="solid",
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
            size=11,
        )

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(
            left=thin,
            right=thin,
            top=thin,
            bottom=thin,
        )

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

            cell.border = border

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

                cell.border = border

        worksheet.column_dimensions["A"].width = 28
        worksheet.column_dimensions["B"].width = 35
        worksheet.column_dimensions["C"].width = 40
        worksheet.column_dimensions["D"].width = 25

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 35

        worksheet.freeze_panes = "A2"

        worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Accesos_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "Accesos",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Accesos_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# INCIDENCIAS
# =========================================================


@admin_bp.route("/incidencias")
@login_required
@role_required("admin")
def incidencias():

    pagina = int(request.args.get("page", 1))
    por_pagina = 15
    total = mongo.db.incidencias.count_documents({})
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    incidencias = list(
        mongo.db.incidencias.find()
        .sort("fecha_hora", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    return render_template(
        "admin_incidencias.html",
        incidencias=incidencias,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# =========================================================
# EXPORTAR INCIDENCIAS PDF
# =========================================================
@admin_bp.route("/incidencias/pdf")
@login_required
@role_required("admin")
def exportar_incidencias_pdf():

    from reportlab.platypus import PageBreak
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle

    incidencias = list(mongo.db.incidencias.find().sort("fecha_hora", -1))

    buffer = BytesIO()

    # =========================================
    # PDF HORIZONTAL
    # =========================================

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elementos = []

    styles = getSampleStyleSheet()

    # =========================================
    # ESTILOS
    # =========================================

    estilo_normal = ParagraphStyle(
        "normal",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#111827"),
    )

    estilo_header = ParagraphStyle(
        "header",
        fontSize=22,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        spaceAfter=20,
    )

    # =========================================
    # TITULO
    # =========================================

    titulo = Paragraph(
        "<b>Reporte de Incidencias</b>",
        estilo_header,
    )

    elementos.append(titulo)

    # =========================================
    # SUBTITULO
    # =========================================

    subtitulo = Paragraph(
        f"""
        <font size=10 color='#475569'>
        Sistema AccessQR<br/>
        Fecha de generación:
        {datetime.now().strftime('%d/%m/%Y %I:%M %p')}
        </font>
        """,
        styles["BodyText"],
    )

    elementos.append(subtitulo)

    elementos.append(Spacer(1, 20))

    # =========================================
    # TABLA
    # =========================================

    data = [
        [
            "Tipo",
            "Guardia",
            "Descripción",
            "Estado",
            "Fecha",
        ]
    ]

    for incidencia in incidencias:

        fecha = incidencia.get("fecha_hora")

        if fecha:
            fecha = fecha.strftime("%d/%m/%Y %I:%M %p")

        else:
            fecha = ""

        descripcion = incidencia.get("descripcion", "Sin descripción")

        data.append(
            [
                Paragraph(
                    incidencia.get("tipo_incidencia", ""),
                    estilo_normal,
                ),
                Paragraph(
                    incidencia.get("guardia_nombre", ""),
                    estilo_normal,
                ),
                Paragraph(
                    descripcion,
                    estilo_normal,
                ),
                Paragraph(
                    incidencia.get("estado", ""),
                    estilo_normal,
                ),
                Paragraph(
                    fecha,
                    estilo_normal,
                ),
            ]
        )

    # =========================================
    # ANCHOS DE COLUMNAS
    # =========================================

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[
            90,
            100,
            320,
            70,
            110,
        ],
    )

    # =========================================
    # ESTILO TABLA
    # =========================================

    tabla.setStyle(
        TableStyle(
            [
                # HEADER
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                # BODY
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#111827")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                # GRID
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
                # ALIGN
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                # PADDING
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                # FILAS ALTERNADAS
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    elementos.append(Spacer(1, 20))

    # =========================================
    # FOOTER
    # =========================================

    footer = Paragraph(
        """
        <font size=8 color='#64748b'>
        Documento generado automáticamente por AccessQR.
        </font>
        """,
        styles["BodyText"],
    )

    elementos.append(footer)

    # =========================================
    # CREAR PDF
    # =========================================

    metadata = _pdf_metadata("Reporte de Incidencias", "Reporte de Incidencias")

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Incidencias_{datetime.now().strftime('%d%m%Y')}.pdf",
        "Incidencias",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Incidencias_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# EXPORTAR INCIDENCIAS EXCEL
# =========================================================


@admin_bp.route("/incidencias/excel")
@login_required
@role_required("admin")
def exportar_incidencias_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    incidencias = list(mongo.db.incidencias.find().sort("fecha_hora", -1))

    data = []

    for incidencia in incidencias:

        fecha = incidencia.get("fecha_hora")

        if fecha:
            fecha = fecha.strftime("%d/%m/%Y %I:%M %p")

        data.append(
            {
                "Tipo Incidencia": incidencia.get("tipo_incidencia", ""),
                "Guardia": incidencia.get("guardia_nombre", ""),
                "Descripción": incidencia.get("descripcion", ""),
                "Estado": incidencia.get("estado", ""),
                "Fecha y Hora": fecha,
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Incidencias", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Incidencias"]

        # =========================================
        # ESTILOS
        # =========================================

        header_fill = PatternFill(
            start_color="0F172A", end_color="0F172A", fill_type="solid"
        )

        header_font = Font(color="FFFFFF", bold=True, size=11)

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # =========================================
        # HEADER
        # =========================================

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

            cell.border = border

        # =========================================
        # BODY
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    vertical="top", horizontal="center", wrap_text=True
                )

                cell.border = border

        # =========================================
        # ANCHO COLUMNAS
        # =========================================

        column_widths = {
            "A": 25,
            "B": 25,
            "C": 70,
            "D": 20,
            "E": 25,
        }

        for col, width in column_widths.items():

            worksheet.column_dimensions[col].width = width

        # =========================================
        # ALTURA FILAS
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 45

        # =========================================
        # FILTROS
        # =========================================

        worksheet.auto_filter.ref = worksheet.dimensions

        # =========================================
        # CONGELAR HEADER
        # =========================================

        worksheet.freeze_panes = "A2"

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Incidencias_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "Incidencias",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Incidencias_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# REPORTES
# =========================================================


@admin_bp.route("/reportes")
@login_required
@role_required("admin")
def reportes():

    return render_template("admin_reportes.html")


# =========================================================
# EXPORTAR VISITAS PDF
# =========================================================


@admin_bp.route("/visitas/pdf")
@login_required
@role_required("admin")
def exportar_visitas_pdf():

    from reportlab.lib.pagesizes import landscape
    from reportlab.lib.styles import ParagraphStyle

    visitas = list(mongo.db.visits.find().sort("created_at", -1))

    buffer = BytesIO()

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elementos = []

    styles = getSampleStyleSheet()

    estilo_normal = ParagraphStyle(
        "normal",
        fontSize=8,
        leading=10,
    )

    titulo = Paragraph(
        "<font size=22><b>Reporte de Visitas</b></font>",
        styles["Title"],
    )

    elementos.append(titulo)

    elementos.append(Spacer(1, 15))

    data = [
        [
            "Visitante",
            "Residente",
            "Placas",
            "Estado",
        ]
    ]

    for visita in visitas:

        placa = ""

        vehiculo = visita.get("vehiculo", {})

        if isinstance(vehiculo, dict):
            placa = vehiculo.get("placa", "")

        estado = visita.get("estado", "")

        estado_map = {
            "activo": "Activo",
            "dentro": "Dentro",
            "salida_registrada": "Finalizada",
            "cancelado": "Cancelado",
            "vencido": "Vencido",
        }

        data.append(
            [
                Paragraph(visita.get("nombre_visitante", ""), estilo_normal),
                Paragraph(visita.get("residente_nombre", ""), estilo_normal),
                Paragraph(placa, estilo_normal),
                Paragraph(estado_map.get(estado, estado), estilo_normal),
            ]
        )

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[260, 260, 120, 120],
    )

    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e1")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    metadata = _pdf_metadata("Reporte de Visitas", "Reporte de Visitas")

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Visitas_{datetime.now().strftime('%d%m%Y')}.pdf",
        "Visitas",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Visitas_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# EXPORTAR VISITAS EXCEL
# =========================================================


@admin_bp.route("/visitas/excel")
@login_required
@role_required("admin")
def exportar_visitas_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    visitas = list(mongo.db.visits.find().sort("created_at", -1))

    data = []

    for visita in visitas:

        placa = ""

        vehiculo = visita.get("vehiculo", {})

        if isinstance(vehiculo, dict):
            placa = vehiculo.get("placa", "")

        estado = visita.get("estado", "")

        estado_map = {
            "activo": "Activo",
            "dentro": "Dentro",
            "salida_registrada": "Finalizada",
            "cancelado": "Cancelado",
            "vencido": "Vencido",
        }

        data.append(
            {
                "Visitante": visita.get("nombre_visitante", ""),
                "Residente": visita.get("residente_nombre", ""),
                "Placas": placa,
                "Estado": estado_map.get(estado, estado),
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Visitas", index=False)

        workbook = writer.book
        worksheet = writer.sheets["Visitas"]

        # =========================================
        # ESTILOS
        # =========================================

        header_fill = PatternFill(
            start_color="0F172A", end_color="0F172A", fill_type="solid"
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
            size=11,
        )

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        # =========================================
        # HEADER
        # =========================================

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

            cell.border = border

        # =========================================
        # BODY
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )

                cell.border = border

        # =========================================
        # ANCHO COLUMNAS
        # =========================================

        worksheet.column_dimensions["A"].width = 35
        worksheet.column_dimensions["B"].width = 35
        worksheet.column_dimensions["C"].width = 20
        worksheet.column_dimensions["D"].width = 20

        # =========================================
        # ALTURA FILAS
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 35

        # =========================================
        # CONGELAR HEADER
        # =========================================

        worksheet.freeze_panes = "A2"

        # =========================================
        # FILTROS
        # =========================================

        worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Visitas_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "Visitas",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Visitas_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# EXPORTAR RESIDENTES EXCEL
# =========================================================


@admin_bp.route("/residentes/excel")
@login_required
@role_required("admin")
def exportar_residentes_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    residentes = list(mongo.db.users.find({"rol": "residente"}))

    data = []

    for residente in residentes:

        data.append(
            {
                "Nombre": residente.get("nombre", ""),
                "Correo": residente.get("correo", ""),
                "Telefono": residente.get("telefono", ""),
                "Privada": residente.get("privada", ""),
                "Casa": residente.get("numero_casa", ""),
                "Estado": residente.get("estado", ""),
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Residentes", index=False)

        worksheet = writer.sheets["Residentes"]

        # =========================================
        # ESTILOS
        # =========================================

        header_fill = PatternFill(
            start_color="0F172A",
            end_color="0F172A",
            fill_type="solid",
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
            size=11,
        )

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(
            left=thin,
            right=thin,
            top=thin,
            bottom=thin,
        )

        # =========================================
        # HEADER
        # =========================================

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

            cell.border = border

        # =========================================
        # BODY
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

                cell.border = border

        # =========================================
        # ANCHO COLUMNAS
        # =========================================

        worksheet.column_dimensions["A"].width = 35
        worksheet.column_dimensions["B"].width = 35
        worksheet.column_dimensions["C"].width = 22
        worksheet.column_dimensions["D"].width = 22
        worksheet.column_dimensions["E"].width = 15
        worksheet.column_dimensions["F"].width = 18

        # =========================================
        # ALTURA FILAS
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 35

        # =========================================
        # CONGELAR HEADER
        # =========================================

        worksheet.freeze_panes = "A2"

        # =========================================
        # FILTROS
        # =========================================

        worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Residentes_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "Residentes",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Residentes_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# EXPORTAR GUARDIAS EXCEL
# =========================================================


@admin_bp.route("/guardias/excel")
@login_required
@role_required("admin")
def exportar_guardias_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    guardias = list(mongo.db.users.find({"rol": "guardia"}))

    data = []

    for guardia in guardias:

        data.append(
            {
                "Nombre": guardia.get("nombre", ""),
                "Correo": guardia.get("correo", ""),
                "Telefono": guardia.get("telefono", ""),
                "Turno": guardia.get("turno", ""),
                "Estado": guardia.get("estado", ""),
            }
        )

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Guardias", index=False)

        worksheet = writer.sheets["Guardias"]

        # =========================================
        # ESTILOS
        # =========================================

        header_fill = PatternFill(
            start_color="0F172A",
            end_color="0F172A",
            fill_type="solid",
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
            size=11,
        )

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(
            left=thin,
            right=thin,
            top=thin,
            bottom=thin,
        )

        # =========================================
        # HEADER
        # =========================================

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

            cell.border = border

        # =========================================
        # BODY
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

                cell.border = border

        # =========================================
        # ANCHO COLUMNAS
        # =========================================

        worksheet.column_dimensions["A"].width = 35
        worksheet.column_dimensions["B"].width = 35
        worksheet.column_dimensions["C"].width = 22
        worksheet.column_dimensions["D"].width = 18
        worksheet.column_dimensions["E"].width = 18

        # =========================================
        # ALTURA FILAS
        # =========================================

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 35

        # =========================================
        # CONGELAR HEADER
        # =========================================

        worksheet.freeze_panes = "A2"

        # =========================================
        # FILTROS
        # =========================================

        worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_Guardias_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "Guardias",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_Guardias_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# EXPORTAR SISTEMA PDF
# =========================================================


@admin_bp.route("/sistema/pdf")
@login_required
@role_required("admin")
def exportar_sistema_pdf():

    total_residentes = mongo.db.users.count_documents({"rol": "residente"})

    total_guardias = mongo.db.users.count_documents({"rol": "guardia"})

    total_visitas = mongo.db.visits.count_documents({})

    total_accesos = mongo.db.access_logs.count_documents({})

    total_incidencias = mongo.db.incidencias.count_documents({})

    buffer = BytesIO()

    from reportlab.lib.pagesizes import landscape

    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    elementos = []

    styles = getSampleStyleSheet()

    # =====================================================
    # TITULO
    # =====================================================

    titulo = Paragraph(
        "<font size=24><b>Reporte General del Sistema</b></font>",
        styles["Title"],
    )

    elementos.append(titulo)

    elementos.append(Spacer(1, 20))

    # =====================================================
    # SUBTITULO
    # =====================================================

    subtitulo = Paragraph(
        f"""
        <font size=11 color='#475569'>
        Sistema AccessQR<br/>
        Fecha de generación:
        {datetime.now().strftime('%d/%m/%Y %I:%M %p')}
        </font>
        """,
        styles["BodyText"],
    )

    elementos.append(subtitulo)

    elementos.append(Spacer(1, 25))

    # =====================================================
    # TABLA
    # =====================================================

    data = [
        ["Módulo", "Total"],
        ["Residentes", total_residentes],
        ["Guardias", total_guardias],
        ["Visitas", total_visitas],
        ["Accesos", total_accesos],
        ["Incidencias", total_incidencias],
    ]

    tabla = Table(
        data,
        repeatRows=1,
        colWidths=[250, 150],
    )

    tabla.setStyle(
        TableStyle(
            [
                # HEADER
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 12),
                # BODY
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 11),
                # GRID
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                # ALIGN
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                # PADDING
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                # FILAS
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
            ]
        )
    )

    elementos.append(tabla)

    elementos.append(Spacer(1, 30))

    # =====================================================
    # FOOTER
    # =====================================================

    footer = Paragraph(
        """
        <font size=9 color='#64748b'>
        Documento generado automáticamente por AccessQR.
        </font>
        """,
        styles["BodyText"],
    )

    elementos.append(footer)

    # =====================================================
    # CREAR PDF
    # =====================================================

    metadata = _pdf_metadata(
        "Reporte General del Sistema", "Reporte General del Sistema"
    )

    pdf.build(elementos, onFirstPage=metadata, onLaterPages=metadata)

    buffer.seek(0)

    _registrar_historial_reporte(
        f"Reporte_General_{datetime.now().strftime('%d%m%Y')}.pdf",
        "General",
        "PDF",
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_General_{datetime.now().strftime('%d%m%Y')}.pdf",
        mimetype="application/pdf",
    )


# =========================================================
# EXPORTAR SISTEMA EXCEL
# =========================================================


@admin_bp.route("/sistema/excel")
@login_required
@role_required("admin")
def exportar_sistema_excel():

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    data = [
        {
            "Módulo": "Residentes",
            "Total": mongo.db.users.count_documents({"rol": "residente"}),
        },
        {
            "Módulo": "Guardias",
            "Total": mongo.db.users.count_documents({"rol": "guardia"}),
        },
        {
            "Módulo": "Visitas",
            "Total": mongo.db.visits.count_documents({}),
        },
        {
            "Módulo": "Accesos",
            "Total": mongo.db.access_logs.count_documents({}),
        },
        {
            "Módulo": "Incidencias",
            "Total": mongo.db.incidencias.count_documents({}),
        },
    ]

    df = pd.DataFrame(data)

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name="Sistema", index=False)

        worksheet = writer.sheets["Sistema"]

        header_fill = PatternFill(
            start_color="0F172A",
            end_color="0F172A",
            fill_type="solid",
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
            size=11,
        )

        thin = Side(border_style="thin", color="CBD5E1")

        border = Border(
            left=thin,
            right=thin,
            top=thin,
            bottom=thin,
        )

        for cell in worksheet[1]:

            cell.fill = header_fill
            cell.font = header_font

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

            cell.border = border

        for row in worksheet.iter_rows(min_row=2):

            for cell in row:

                cell.alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                    wrap_text=True,
                )

                cell.border = border

        worksheet.column_dimensions["A"].width = 35
        worksheet.column_dimensions["B"].width = 20

        for row in worksheet.iter_rows(min_row=2):

            worksheet.row_dimensions[row[0].row].height = 30

        worksheet.freeze_panes = "A2"

        worksheet.auto_filter.ref = worksheet.dimensions

    output.seek(0)

    _registrar_historial_reporte(
        f"Reporte_General_{datetime.now().strftime('%d%m%Y')}.xlsx",
        "General",
        "Excel",
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Acceso_QR_Reporte_General_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# HISTORIAL DE REPORTES
# =========================================================


@admin_bp.route("/historial-reportes")
@login_required
@role_required("admin")
def historial_reportes():

    pagina = int(request.args.get("page", 1))
    por_pagina = 15
    total = mongo.db.reportes.count_documents({})
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)

    reportes = list(
        mongo.db.reportes.find()
        .sort("fecha", -1)
        .skip((pagina - 1) * por_pagina)
        .limit(por_pagina)
    )

    for r in reportes:
        if isinstance(r.get("fecha"), datetime):
            r["fecha"] = r["fecha"].strftime("%d/%m/%Y %I:%M %p")

    return render_template(
        "admin_historial_reportes.html",
        reportes=reportes,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# =========================================================
# CONFIGURACIÓN
# =========================================================


@admin_bp.route("/configuracion")
@login_required
@role_required("admin")
def configuracion():

    return render_template("admin_configuracion.html")
