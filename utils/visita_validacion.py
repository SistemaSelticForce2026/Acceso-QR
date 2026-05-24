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
        vigencia_hasta = visita.get("vigencia_hasta")
        if vigencia_hasta and isinstance(vigencia_hasta, datetime):
            if ahora > vigencia_hasta:
                return (
                    False,
                    "El QR recurrente venció. Debe generarse uno nuevo cada mes.",
                )

        dia = (visita.get("dia_semana") or "").strip().lower()
        dia_num = DIAS_SEMANA_MAP.get(dia)
        if dia_num is None:
            return False, "Día de la visita recurrente no configurado."

        if ahora.weekday() != dia_num:
            return (
                False,
                f"Este QR solo es válido los {dia.capitalize()}.",
            )

        hora_prog = _parse_time(
            visita.get("hora_programada") or visita.get("hora_inicio")
        )
        if hora_prog:
            ventana_inicio = (
                datetime.combine(ahora.date(), hora_prog) - timedelta(minutes=30)
            ).time()
            if ahora.time() < ventana_inicio:
                return (
                    False,
                    f"El acceso está autorizado a partir de las {hora_prog.strftime('%H:%M')}.",
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
    """Marca QR recurrente como vencido si pasó el mes de vigencia."""
    if visita.get("modalidad_visita") != "recurrente":
        return
    vigencia_hasta = visita.get("vigencia_hasta")
    if vigencia_hasta and isinstance(vigencia_hasta, datetime):
        if datetime.now() > vigencia_hasta:
            from extensions import mongo

            mongo.db.visits.update_one(
                {"_id": visita_id},
                {"$set": {"qr_estado": "vencido"}},
            )
