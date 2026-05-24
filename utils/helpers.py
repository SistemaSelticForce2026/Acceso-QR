from datetime import datetime


def current_datetime():
    return datetime.now()


def format_datetime(fecha):
    if not fecha:
        return ""
    return fecha.strftime("%d/%m/%Y %H:%M")
