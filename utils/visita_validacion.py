"""Utilidades para validación de acceso mediante QR."""

from datetime import datetime, timedelta, timezone
from extensions import mongo
from utils.fraccionamientos import coleccion_visitas

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


# ---------------------------------------------------------------------------
# Zona horaria del negocio (Centro de México)
# ---------------------------------------------------------------------------

try:
    from zoneinfo import ZoneInfo

    TZ_LOCAL = ZoneInfo("America/Mexico_City")
except (ImportError, KeyError):
    TZ_LOCAL = timezone(timedelta(hours=-6))


def _ahora_local():
    """Hora actual en México, como datetime naive (consistente con el resto
    del sistema, que guarda fechas/horas sin tz)."""
    return datetime.now(TZ_LOCAL).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Tolerancia de horario para visitas recurrentes
# ---------------------------------------------------------------------------
# Colchón para absorber pequeños desfases entre el reloj del guardia y el
# del servidor. Solo aplica a la validación de HORA de visitas recurrentes:
# las visitas temporales no comparan hora, solo fecha, así que no les afecta.
# Cambia este número si quieres más o menos margen.
TOLERANCIA_HORARIO_MIN = 5


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
    """Calcula el rango de vigencia en meses a partir de hoy."""
    inicio = datetime.now()
    fin = inicio + timedelta(days=30 * meses)
    return inicio, fin


def visita_no_presentada_hoy(visita, ahora=None):
    """Indica si una visita RECURRENTE 'no se presentó' en el día de hoy:
    hoy es día autorizado, ya pasó la hora_desde de hoy (mismo criterio que
    se usa para temporales: se dispara apenas pasa la hora programada de
    inicio, sin esperar a que cierre toda la ventana), el visitante no está
    dentro y no entró hoy en este ciclo. No aplica a temporales."""
    if ahora is None:
        ahora = _ahora_local()

    if visita.get("modalidad_visita") != "recurrente":
        return False

    if visita.get("estado") == "dentro":
        return False

    dias_autorizados = [
        d.lower() for d in (visita.get("dias_autorizados") or visita.get("dias") or [])
    ]
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
        return False

    hora_desde = _parse_time(visita.get("hora_desde"))
    if not hora_desde or ahora.time() <= hora_desde:
        return False

    fecha_entrada = visita.get("fecha_entrada_real")
    if isinstance(fecha_entrada, datetime) and fecha_entrada.date() == ahora.date():
        return False

    return True


def validar_acceso_qr(visita):
    """
    Valida si el QR puede usarse para una nueva entrada.
    Retorna (valido: bool, mensaje: str).
    """
    ahora = _ahora_local()
    modalidad = visita.get("modalidad_visita", "temporal")

    if visita.get("qr_estado") in ("vencido", "cancelado", "finalizado"):
        return False, "QR no válido o ya finalizado."

    if modalidad == "recurrente":

        if visita.get("estado_recurrente") == "suspendido":
            return (False, "El permiso recurrente se encuentra suspendido.")

        fecha_inicio = _parse_fecha(visita.get("fecha_inicio_recurrente"))
        fecha_fin = _parse_fecha(visita.get("fecha_fin_recurrente"))

        if fecha_inicio and ahora.date() < fecha_inicio:
            return (False, "La autorización aún no inicia.")

        if fecha_fin and ahora.date() > fecha_fin:
            return (False, "La autorización ya venció.")

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

        hora_desde = _parse_time(visita.get("hora_desde"))
        hora_hasta = _parse_time(visita.get("hora_hasta"))

        # Colchón de tolerancia: se compara la hora actual +/- el margen
        # contra los límites reales del horario, sin modificar los límites
        # que se muestran al usuario (esos siguen siendo los originales).
        tolerancia = timedelta(minutes=TOLERANCIA_HORARIO_MIN)

        if hora_desde:
            desde_dt = datetime.combine(ahora.date(), hora_desde)
            if ahora < desde_dt - tolerancia:
                return (
                    False,
                    f"Acceso permitido a partir de las {hora_desde.strftime('%H:%M')}.",
                )

        if hora_hasta:
            hasta_dt = datetime.combine(ahora.date(), hora_hasta)
            if ahora > hasta_dt:
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
    """Marca QR recurrente como vencido si pasó el mes de vigencia."""
    if visita.get("modalidad_visita") != "recurrente":
        return
    vigencia_hasta = visita.get("vigencia_hasta")
    if vigencia_hasta and isinstance(vigencia_hasta, datetime):
        if datetime.now() > vigencia_hasta:
            col = coleccion_visitas(mongo.db, visita.get("fraccionamiento"))
            if col is not None:
                col.update_one(
                    {"_id": visita_id},
                    {"$set": {"qr_estado": "vencido"}},
                )
