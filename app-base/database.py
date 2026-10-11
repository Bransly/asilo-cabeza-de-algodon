import os
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "asilo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "db_asilo")

if DB_HOST:
    URL_BASE_DATOS = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        "?charset=utf8mb4"
    )
else:
    # Sin MySQL (desarrollo fuera de Docker) se usa SQLite.
    URL_BASE_DATOS = os.getenv("DATABASE_URL", "sqlite:///asilo.db")

motor = create_engine(URL_BASE_DATOS, pool_pre_ping=True, future=True)
Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def crear_tablas(intentos: int = 12, espera: int = 5) -> None:
    """MySQL en Docker tarda en aceptar conexiones: se reintenta."""
    import models  # noqa: F401  (registra las clases en el metadata)

    for intento in range(1, intentos + 1):
        try:
            Base.metadata.create_all(bind=motor)
            return
        except OperationalError as error:
            if intento == intentos:
                raise
            print(f"[base de datos] intento {intento}/{intentos}: {error.orig}")
            time.sleep(espera)
