"""
Punto de entrada para Gunicorn (servidor de produccion).

Gunicorn se ejecuta con --preload: este modulo se importa una sola vez en el
proceso principal, de modo que la creacion de tablas y la carga inicial no se
repiten en cada trabajador.
"""
from app import app, preparar_base_de_datos

preparar_base_de_datos()

__all__ = ["app"]
