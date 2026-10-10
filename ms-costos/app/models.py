"""
CAPA DE ENTIDADES / MODELOS
Clases que representan los conceptos del negocio. No contienen reglas de negocio.
Corresponden a las entidades Cobro / CuentaFamiliar del ERD del proyecto.
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, Numeric, String

from .database import Base


def Dinero():
    """DECIMAL(10,2) en MySQL: los centavos se guardan exactos, nunca como FLOAT."""
    return Numeric(10, 2, asdecimal=True)


def Porcentaje():
    """DECIMAL(5,2): de 0.00 a 100.00."""
    return Numeric(5, 2, asdecimal=True)


class TipoServicio(str, enum.Enum):
    CONSULTA = "CONSULTA"
    EXAMEN = "EXAMEN"
    MEDICAMENTO = "MEDICAMENTO"


class EstadoCargo(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"


class Tarifa(Base):
    """Precio de referencia de la fundacion y el descuento que otorga al asilo."""

    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    descripcion = Column(String(150), nullable=False)
    precio_base = Column(Dinero(), nullable=False)
    descuento_fundacion = Column(Porcentaje(), nullable=False, default=0)  # 0-100
    activo = Column(Boolean, nullable=False, default=True)


class Cargo(Base):
    """Cargo generado a la cuenta del familiar por consulta, examen o medicamento."""

    __tablename__ = "cargos"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, nullable=False, index=True)
    paciente_nombre = Column(String(120), nullable=False)
    visita_id = Column(Integer, nullable=True)
    tarifa_id = Column(Integer, nullable=True)

    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    descripcion = Column(String(150), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)

    # Precio y descuento se COPIAN de la tarifa al crear el cargo: si la
    # fundacion cambia su tarifa despues, el cargo conserva su monto original.
    precio_base = Column(Dinero(), nullable=False)
    descuento_aplicado = Column(Porcentaje(), nullable=False, default=0)  # porcentaje
    subtotal = Column(Dinero(), nullable=False)   # precio_base * cantidad
    total = Column(Dinero(), nullable=False)      # subtotal menos descuento

    estado = Column(Enum(EstadoCargo), nullable=False, default=EstadoCargo.PENDIENTE)
    fecha_registro = Column(DateTime, nullable=False, default=datetime.now)
    fecha_pago = Column(DateTime, nullable=True)
    # Si un pago se revierte por error, queda el motivo de la ultima reversion.
    motivo_reversion = Column(String(200), nullable=True)
