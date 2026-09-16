"""
ESQUEMAS (DTO)
Definen que datos entran y que datos salen por la API. Validan formato y tipo,
nunca reglas del negocio. Esto separa el contrato publico del modelo interno.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import EstadoCargo, TipoServicio


# ---------- Tarifas ----------
class TarifaCrear(BaseModel):
    tipo_servicio: TipoServicio
    descripcion: str = Field(min_length=3, max_length=150)
    precio_base: float = Field(gt=0)
    descuento_fundacion: float = Field(default=0.0, ge=0, le=100)
    activo: bool = True


class TarifaActualizar(BaseModel):
    descripcion: Optional[str] = Field(default=None, min_length=3, max_length=150)
    precio_base: Optional[float] = Field(default=None, gt=0)
    descuento_fundacion: Optional[float] = Field(default=None, ge=0, le=100)
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
