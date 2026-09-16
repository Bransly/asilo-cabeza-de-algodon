"""
CAPA DE ACCESO A DATOS - Conexion
Unico punto del microservicio que conoce el motor de base de datos (MySQL).
Ninguna otra capa importa SQLAlchemy directamente.
"""
import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# La cadena de conexion se lee de variables de entorno (nunca quemada en el codigo).
DB_USER = os.getenv("DB_USER", "asilo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "asilo123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "db_costos")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Clase base de la que heredan todas las entidades (capa de Entidades/Modelos).
Base = declarative_base()


def get_db():
    """Entrega una sesion de base de datos y garantiza que se cierre siempre."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(intentos: int = 15, espera: int = 3) -> None:
    """
    Crea las tablas al arrancar el contenedor.
    MySQL tarda unos segundos en aceptar conexiones, por eso se reintenta.
    """
    from . import models  # noqa: F401  (registra las entidades en Base.metadata)

    for intento in range(1, intentos + 1):
        try:
            Base.metadata.create_all(bind=engine)
            print(f"[ms-costos] Base de datos lista en {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return
        except Exception as error:
            print(f"[ms-costos] MySQL no responde (intento {intento}/{intentos}): {error}")
            time.sleep(espera)
    raise RuntimeError("No fue posible conectar con MySQL")
