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
# DASHBOARD ADMIN
# =========================================================


@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():

    from collections import Counter

    filtro = request.args.get("filtro", "hoy")

    busqueda = request.args.get("busqueda", "").strip()

    fecha_inicio_tabla = request.args.get("fecha_inicio_tabla", "").strip()

    fecha_fin_tabla = request.args.get("fecha_fin_tabla", "").strip()

    hoy = datetime.now()

    if filtro == "hoy":

        fecha_inicio = datetime(hoy.year, hoy.month, hoy.day)

    elif filtro == "semana":

        fecha_inicio = hoy - timedelta(days=7)

    elif filtro == "mes":

        fecha_inicio = hoy - timedelta(days=30)

    else:

        fecha_inicio = datetime(hoy.year, hoy.month, hoy.day)

    visitas = list(
        mongo.db.visits.find({"created_at": {"$gte": fecha_inicio}}).sort(
            "created_at", -1
        )
    )

    accesos = list(mongo.db.access_logs.find().sort("fecha_hora", -1))

    accesos = [
        a for a in accesos if a.get("fecha_hora") and a["fecha_hora"] >= fecha_inicio
    ]

    incidencias = list(mongo.db.incidencias.find().sort("fecha_hora", -1))

    incidencias = [
        i
        for i in incidencias
        if i.get("fecha_hora") and i["fecha_hora"] >= fecha_inicio
    ]

    if busqueda:
        busqueda_lower = busqueda.lower()
        visitas = [v for v in visitas if busqueda_lower in v.get("nombre_visitante", "").lower() or busqueda_lower in v.get("residente_nombre", "").lower()]
        accesos = [a for a in accesos if busqueda_lower in a.get("visitante", "").lower() or busqueda_lower in a.get("guardia_nombre", "").lower() or busqueda_lower in a.get("accion", "").lower()]
        incidencias = [i for i in incidencias if busqueda_lower in i.get("visitante", "").lower() or busqueda_lower in i.get("guardia_nombre", "").lower() or busqueda_lower in i.get("descripcion", "").lower()]

    # Filtro de fechas para la tabla de visitas (calendarios independientes)
    visitas_tabla = visitas

    if fecha_inicio_tabla:
        visitas_tabla = [v for v in visitas_tabla if v.get("fecha_visita", "") >= fecha_inicio_tabla]

    if fecha_fin_tabla:
        visitas_tabla = [v for v in visitas_tabla if v.get("fecha_visita", "") <= fecha_fin_tabla]

    pagina_tabla = int(request.args.get("page", 1))
    por_pagina_tabla = 5
    total_visitas_tabla = len(visitas_tabla)
    total_paginas_tabla = max(1, (total_visitas_tabla + por_pagina_tabla - 1) // por_pagina_tabla)
    
    visitas_tabla_paginada = visitas_tabla[(pagina_tabla - 1) * por_pagina_tabla : pagina_tabla * por_pagina_tabla]

    # =====================================================
    # KPIs
    # =====================================================

    total_visitas = len(visitas)

    dentro = len([v for v in visitas if v.get("estado") == "dentro"])

    activas = len([v for v in visitas if v.get("estado") == "activo"])

    salidas = len([v for v in visitas if v.get("estado") == "salida_registrada"])

    total_residentes = mongo.db.users.count_documents({"rol": "residente"})

    total_guardias = mongo.db.users.count_documents({"rol": "guardia"})

    total_incidencias = len(incidencias)

    rechazados = len([a for a in accesos if a.get("resultado") == "rechazado"])

    # =====================================================
    # TIPOS VISITA
    # =====================================================

    tipos_counter = Counter()

    for visita in visitas:

        tipo = visita.get("modalidad_visita") or visita.get("tipo_visita", "General")

        tipos_counter[tipo] += 1

    tipo_labels = list(tipos_counter.keys())
    tipo_data = list(tipos_counter.values())

    # =====================================================
    # VISITAS POR DIA (ORDENADO Y PROFESIONAL)
    # =====================================================

    dias_counter = Counter()

    for visita in visitas:

        fecha = visita.get("fecha_visita")

        if fecha:

            dias_counter[str(fecha)] += 1

    # ==========================================
    # ORDENAR FECHAS CRONOLOGICAMENTE
    # ==========================================

    fechas_ordenadas = sorted(
        dias_counter.keys(), key=lambda x: datetime.strptime(x, "%Y-%m-%d")
    )

    # ==========================================
    # FORMATO BONITO PARA LA GRAFICA
    # 31/05 -> 01/06 -> 02/06
    # ==========================================

    dias_labels = [
        datetime.strptime(fecha, "%Y-%m-%d").strftime("%d/%m")
        for fecha in fechas_ordenadas
    ]

    dias_data = [dias_counter[fecha] for fecha in fechas_ordenadas]

    # =====================================================
    # TOP RESIDENTES
    # =====================================================

    residentes_counter = Counter()

    for visita in visitas:

        residente = visita.get("residente_nombre", "Sin residente")

        residentes_counter[residente] += 1

    top_residentes = residentes_counter.most_common(5)

    # =====================================================
    # ACTIVIDAD RECIENTE
    # =====================================================

    actividad_reciente = accesos[:5]

    # =====================================================
    # HORAS PICO
    # =====================================================

    horas_counter = Counter()

    for acceso in accesos:

        fecha = acceso.get("fecha_hora")

        if fecha:

            hora = fecha.strftime("%I %p")

            horas_counter[hora] += 1

    horas_ordenadas = sorted(
        horas_counter.items(), key=lambda x: datetime.strptime(x[0], "%I %p")
    )

    horas_labels = [h[0] for h in horas_ordenadas]

    horas_data = [h[1] for h in horas_ordenadas]

    # =====================================================
    # VISITAS POR PRIVADA
    # =====================================================

    privadas_counter = Counter()

    for visita in visitas:

        privada = visita.get("condominio", "General")

        privadas_counter[privada] += 1

    privadas_labels = list(privadas_counter.keys())

    privadas_data = list(privadas_counter.values())

    # =====================================================
    # VISITAS DENTRO
    # =====================================================

    visitas_dentro = [v for v in visitas if v.get("estado") == "dentro"]

    # =====================================================
    # ALERTAS AUTOMATICAS
    # =====================================================

    alertas = []

    if rechazados >= 5:

        alertas.append("Demasiados QR rechazados")

    if dentro >= 20:

        alertas.append("Muchas personas dentro")

    # =====================================================
    # SEGURIDAD
    # =====================================================

    accesos_rechazados = [a for a in accesos if a.get("resultado") == "rechazado"][:10]

    # =====================================================
    # TOP GUARDIAS
    # =====================================================

    guardias_counter = Counter()

    for acceso in accesos:

        guardia = acceso.get("guardia_nombre", "Desconocido")

        guardias_counter[guardia] += 1

    top_guardias = guardias_counter.most_common(5)

    # =====================================================
    # RESIDENTES ACTIVOS
    # =====================================================

    residentes_activos = residentes_counter.most_common(10)

    # =====================================================
    # VEHICULOS FRECUENTES
    # =====================================================

    vehiculos = []

    for visita in visitas:

        vehiculo = visita.get("vehiculo")

        if vehiculo:

            placa = vehiculo.get("placa")

            if placa:

                vehiculos.append(placa)

    vehiculos = list(set(vehiculos))

    # =====================================================
    # ANALITICA
    # =====================================================

    if filtro == "hoy":

        promedio = total_visitas

    elif filtro == "semana":

        promedio = round(total_visitas / 7, 2)

    else:

        promedio = round(total_visitas / 30, 2)

    return render_template(
        "admin_dashboard.html",
        filtro=filtro,
        visitas=visitas,
        accesos=accesos,
        incidencias=incidencias,
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
        total_paginas=total_paginas
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

        socketio.emit("actualizar_residentes")

        socketio.emit("actualizar_dashboard")

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

        socketio.emit("actualizar_residentes")

        socketio.emit("actualizar_dashboard")

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

    socketio.emit("actualizar_residentes")

    socketio.emit("actualizar_dashboard")

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

    socketio.emit("actualizar_residentes")

    socketio.emit("actualizar_dashboard")

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

    socketio.emit("actualizar_residentes")

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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"residentes_{datetime.now().strftime('%d%m%Y')}.pdf",
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
        total_paginas=total_paginas
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

        socketio.emit("actualizar_guardias")

        socketio.emit("actualizar_dashboard")

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

        socketio.emit("actualizar_guardias")

        socketio.emit("actualizar_dashboard")

        flash("Guardia actualizado correctamente")

        return redirect(url_for("admin.guardias"))

    return render_template("editar_guardia.html", guardia=guardia)


@admin_bp.route("/guardias/desactivar/<id>")
@login_required
@role_required("admin")
def desactivar_guardia(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "inactivo"}})

    socketio.emit("actualizar_guardias")

    socketio.emit("actualizar_dashboard")

    flash("Guardia desactivado correctamente")

    return redirect(url_for("admin.guardias"))


@admin_bp.route("/guardias/activar/<id>")
@login_required
@role_required("admin")
def activar_guardia(id):

    mongo.db.users.update_one({"_id": ObjectId(id)}, {"$set": {"estado": "activo"}})

    socketio.emit("actualizar_guardias")

    socketio.emit("actualizar_dashboard")

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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"guardias_{datetime.now().strftime('%d%m%Y')}.pdf",
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
        total_paginas=total_paginas
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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"accesos_{datetime.now().strftime('%d%m%Y')}.pdf",
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"accesos_{datetime.now().strftime('%d%m%Y')}.xlsx",
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
        total_paginas=total_paginas
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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"incidencias_{datetime.now().strftime('%d%m%Y')}.pdf",
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"incidencias_{datetime.now().strftime('%d%m%Y')}.xlsx",
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

        data.append(
            [
                Paragraph(visita.get("nombre_visitante", ""), estilo_normal),
                Paragraph(visita.get("residente_nombre", ""), estilo_normal),
                Paragraph(visita.get("placas", ""), estilo_normal),
                Paragraph(visita.get("estado", ""), estilo_normal),
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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"visitas_{datetime.now().strftime('%d%m%Y')}.pdf",
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

        data.append(
            {
                "Visitante": visita.get("nombre_visitante", ""),
                "Residente": visita.get("residente_nombre", ""),
                "Placas": visita.get("placas", ""),
                "Estado": visita.get("estado", ""),
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"visitas_{datetime.now().strftime('%d%m%Y')}.xlsx",
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"residentes_{datetime.now().strftime('%d%m%Y')}.xlsx",
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"guardias_{datetime.now().strftime('%d%m%Y')}.xlsx",
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

    pdf.build(elementos)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"sistema_{datetime.now().strftime('%d%m%Y')}.pdf",
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

    return send_file(
        output,
        as_attachment=True,
        download_name=f"sistema_{datetime.now().strftime('%d%m%Y')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =========================================================
# HISTORIAL DE REPORTES
# =========================================================


@admin_bp.route("/historial-reportes")
@login_required
@role_required("admin")
def historial_reportes():

    reportes = [
        {
            "nombre": "visitas_17052026.pdf",
            "tipo": "Visitas",
            "formato": "PDF",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:45 PM",
            "estado": "Generado",
        },
        {
            "nombre": "visitas_17052026.xlsx",
            "tipo": "Visitas",
            "formato": "Excel",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:42 PM",
            "estado": "Generado",
        },
        {
            "nombre": "accesos_17052026.pdf",
            "tipo": "Accesos",
            "formato": "PDF",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:35 PM",
            "estado": "Generado",
        },
        {
            "nombre": "accesos_17052026.xlsx",
            "tipo": "Accesos",
            "formato": "Excel",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:31 PM",
            "estado": "Generado",
        },
        {
            "nombre": "incidencias_17052026.pdf",
            "tipo": "Incidencias",
            "formato": "PDF",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:28 PM",
            "estado": "Generado",
        },
        {
            "nombre": "guardias_17052026.xlsx",
            "tipo": "Guardias",
            "formato": "Excel",
            "usuario": "Administrador",
            "fecha": "17/05/2026 11:20 PM",
            "estado": "Generado",
        },
    ]

    return render_template("admin_historial_reportes.html", reportes=reportes)


# =========================================================
# CONFIGURACIÓN
# =========================================================


@admin_bp.route("/configuracion")
@login_required
@role_required("admin")
def configuracion():

    return render_template("admin_configuracion.html")
