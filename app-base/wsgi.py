from app import app, preparar_base_de_datos
from database import motor

preparar_base_de_datos()
# Los trabajadores de Gunicorn (--preload) no deben heredar las conexiones del
# proceso principal: compartirian sockets de MySQL y se mezclarian las respuestas.
motor.dispose()

__all__ = ["app"]
