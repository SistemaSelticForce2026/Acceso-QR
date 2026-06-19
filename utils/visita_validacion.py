from datetime import datetime, timedelta

DIAS_SEMANA_MAP = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

MODALIDAD_LABELS = {
    "temporal": "Visita temporal",
    "recurrente": "Visita recurrente",
}


def _parse_time(valor):
    if not valor:
        return None
    for formato in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(str(valor), formato).time()
        except ValueError:
            pass
    return None


def _parse_fecha(valor):
    if not valor:
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor), formato).date()
        except ValueError:
            pass
    return None


def vigencia_recurrente_meses(meses=1):
    inicio = datetime.now()
    fin = inicio + timedelta(days=30 * meses)
    return inicio, fin


def validar_acceso_qr(visita):
    """
    Valida si el QR puede usarse para una nueva entrada.
    Retorna (valido: bool, mensaje: str).
    """
    ahora = datetime.now()
    modalidad = visita.get("modalidad_visita", "temporal")

    if visita.get("qr_estado") in ("vencido", "cancelado", "finalizado"):
        return False, "QR no válido o ya finalizado."

    if modalidad == "recurrente":

        # ==========================
        # ESTADO
        # ==========================

        if visita.get("estado_recurrente") == "suspendido":

            return (False, "El permiso recurrente se encuentra suspendido.")

        # ==========================
        # FECHAS
        # ==========================

        fecha_inicio = _parse_fecha(visita.get("fecha_inicio_recurrente"))

        fecha_fin = _parse_fecha(visita.get("fecha_fin_recurrente"))

        if fecha_inicio and ahora.date() < fecha_inicio:

            return (False, "La autorización aún no inicia.")

        if fecha_fin and ahora.date() > fecha_fin:

            return (False, "La autorización ya venció.")

        # ==========================
        # DIAS
        # ==========================

        dias_autorizados = [d.lower() for d in visita.get("dias_autorizados", [])]

        dias_hoy = [
            "lunes",
            "martes",
            "miercoles",
            "jueves",
            "viernes",
            "sabado",
            "domingo",
        ]

        dia_actual = dias_hoy[ahora.weekday()]

        if dias_autorizados and dia_actual not in dias_autorizados:

            return (False, f"Acceso no permitido los {dia_actual.capitalize()}.")

        # ==========================
        # HORARIO
        # ==========================

        hora_desde = _parse_time(visita.get("hora_desde"))

        hora_hasta = _parse_time(visita.get("hora_hasta"))

        if hora_desde and ahora.time() < hora_desde:

            return (
                False,
                f"Acceso permitido a partir de las {hora_desde.strftime('%H:%M')}.",
            )

        if hora_hasta and ahora.time() > hora_hasta:

            return (
                False,
                f"El horario autorizado finalizó a las {hora_hasta.strftime('%H:%M')}.",
            )

        return True, ""

    fecha_prog = _parse_fecha(visita.get("fecha_visita"))
    if fecha_prog and ahora.date() != fecha_prog:
        return (
            False,
            f"Este QR temporal solo es válido el día {visita.get('fecha_visita')}.",
        )

    if visita.get("entrada_consumida"):
        return (
            False,
            "Este QR temporal ya fue utilizado (un solo acceso por visita).",
        )

    return True, ""


def actualizar_qr_vencido_si_aplica(visita_id, visita):
    """Marca QR recurrente como vencido si pasó el mes de vigencia.
    Escribe en la colección de visitas del fraccionamiento de la visita."""
    if visita.get("modalidad_visita") != "recurrente":
        return
    vigencia_hasta = visita.get("vigencia_hasta")
    if vigencia_hasta and isinstance(vigencia_hasta, datetime):
        if datetime.now() > vigencia_hasta:
            from extensions import mongo
            from utils.fraccionamientos import coleccion_visitas

            col = coleccion_visitas(mongo.db, visita.get("fraccionamiento"))
            if col is not None:
                col.update_one(
                    {"_id": visita_id},
                    {"$set": {"qr_estado": "vencido"}},
                )
