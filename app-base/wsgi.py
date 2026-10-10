"""
Punto de entrada para Gunicorn (servidor de produccion).

Gunicorn se ejecuta con --preload: este modulo se importa una sola vez en el
proceso principal, de modo que la creacion de tablas y la carga inicial no se
repiten en cada trabajador.

Despues de preparar la base se descartan las conexiones abiertas. Si no, los
procesos trabajadores (que se crean copiando al principal) heredarian los
mismos sockets de MySQL y, con varias peticiones a la vez, se mezclarian sus
respuestas ("MySQL server has gone away"). Cada trabajador abre las suyas.
"""
from app import app, preparar_base_de_datos
from database import motor

preparar_base_de_datos()
motor.dispose()

__all__ = ["app"]
