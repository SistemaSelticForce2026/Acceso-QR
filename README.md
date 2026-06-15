# Access QR

Sistema de control de acceso residencial con códigos QR (Flask + MongoDB).

## Requisitos

- Python 3.10+
- MongoDB Atlas (o MongoDB local)

## Instalación

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy config.example.py config.py   # Windows
# Edita config.py con tu MONGO_URI y SECRET_KEY
python crear_usuarios.py
python app.py
```

## Roles

- **Residente:** registra visitas y genera QR
- **Guardia:** escaneo de entrada y salida
- **Administrador:** gestión y reportes

## Repositorio

https://github.com/Jesus-Granda/Access-QRD
