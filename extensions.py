from flask_pymongo import PyMongo

from flask_socketio import SocketIO

import certifi

# =====================================================
# MONGODB
# =====================================================

mongo = PyMongo(tlsCAFile=certifi.where())


# =====================================================
# SOCKET.IO
# =====================================================

socketio = SocketIO()
