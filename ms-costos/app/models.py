import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, Numeric, String

from .database import Base


def Dinero():
    return Numeric(10, 2, asdecimal=True)


def Porcentaje():
    return Numeric(5, 2, asdecimal=True)


class TipoServicio(str, enum.Enum):
    CONSULTA = "CONSULTA"
    EXAMEN = "EXAMEN"
    MEDICAMENTO = "MEDICAMENTO"


class EstadoCargo(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    descripcion = Column(String(150), nullable=False)
    precio_base = Column(Dinero(), nullable=False)
    descuento_fundacion = Column(Porcentaje(), nullable=False, default=0)  # 0-100
    activo = Column(Boolean, nullable=False, default=True)


class Cargo(Base):
    __tablename__ = "cargos"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, nullable=False, index=True)
    paciente_nombre = Column(String(120), nullable=False)
    visita_id = Column(Integer, nullable=True)
    tarifa_id = Column(Integer, nullable=True)

    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    descripcion = Column(String(150), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)

    # Se copian de la tarifa: si la fundacion la cambia, el cargo conserva su monto.
    precio_base = Column(Dinero(), nullable=False)
    descuento_aplicado = Column(Porcentaje(), nullable=False, default=0)
    subtotal = Column(Dinero(), nullable=False)   # precio_base * cantidad
    total = Column(Dinero(), nullable=False)      # subtotal menos descuento

    estado = Column(Enum(EstadoCargo), nullable=False, default=EstadoCargo.PENDIENTE)
    fecha_registro = Column(DateTime, nullable=False, default=datetime.now)
    fecha_pago = Column(DateTime, nullable=True)
    # Si un pago se revierte por error, queda el motivo de la ultima reversion.
    motivo_reversion = Column(String(200), nullable=True)
