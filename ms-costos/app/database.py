import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_USER = os.getenv("DB_USER", "asilo")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "db_costos")

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(intentos: int = 15, espera: int = 3) -> None:
    """MySQL tarda en aceptar conexiones: se reintenta."""
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
