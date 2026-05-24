def validar_placa(placa):
    if not placa:
        return True
    return len(placa.strip()) >= 5


def validar_telefono(telefono):
    return telefono.isdigit() and len(telefono) >= 10
