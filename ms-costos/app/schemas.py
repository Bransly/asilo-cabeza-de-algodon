"""
ESQUEMAS (DTO)
Definen que datos entran y que datos salen por la API. Validan formato y tipo,
nunca reglas del negocio. Esto separa el contrato publico del modelo interno.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import EstadoCargo, TipoServicio


# ---------- Tarifas ----------
# Reglas de validacion RV-01 a RV-04: montos positivos con dos decimales como
# maximo y descuento entre 0 y 100. Pydantic rechaza con 422 cualquier valor
# fuera de rango, aunque la peticion llegue directo a la API sin pasar por la
# pantalla.
Precio = Field(gt=0, le=Decimal("99999.99"), max_digits=7, decimal_places=2)
Descuento = Field(ge=0, le=100, max_digits=5, decimal_places=2)


class TarifaCrear(BaseModel):
    tipo_servicio: TipoServicio
    descripcion: str = Field(min_length=3, max_length=150)
    precio_base: Decimal = Precio
    descuento_fundacion: Decimal = Field(default=Decimal("0"), ge=0, le=100,
                                         max_digits=5, decimal_places=2)
    activo: bool = True


class TarifaActualizar(BaseModel):
    descripcion: Optional[str] = Field(default=None, min_length=3, max_length=150)
    precio_base: Optional[Decimal] = Field(default=None, gt=0, le=Decimal("99999.99"),
                                           max_digits=7, decimal_places=2)
    descuento_fundacion: Optional[Decimal] = Field(default=None, ge=0, le=100,
                                                   max_digits=5, decimal_places=2)
    activo: Optional[bool] = None


class TarifaRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo_servicio: TipoServicio
    descripcion: str
    precio_base: float
    descuento_fundacion: float
    activo: bool


# ---------- Cargos ----------
class CargoCrear(BaseModel):
    paciente_id: int = Field(gt=0)
    paciente_nombre: str = Field(min_length=3, max_length=120)
    tarifa_id: int = Field(gt=0)
    cantidad: int = Field(default=1, gt=0, le=500)
    visita_id: Optional[int] = None


class CargoRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    paciente_nombre: str
    visita_id: Optional[int]
    tipo_servicio: TipoServicio
    descripcion: str
    cantidad: int
    precio_base: float
    descuento_aplicado: float
    subtotal: float
    total: float
    estado: EstadoCargo
    fecha_registro: datetime
    fecha_pago: Optional[datetime] = None
    motivo_reversion: Optional[str] = None


class ReversionPago(BaseModel):
    motivo: str = Field(min_length=5, max_length=200)


class EstadoCuenta(BaseModel):
    """Salida del reporte de cobros por paciente exigido en el enunciado."""

    paciente_id: int
    paciente_nombre: str
    cantidad_cargos: int
    total_sin_descuento: float
    total_ahorrado: float
    total_facturado: float
    total_pagado: float
    saldo_pendiente: float
