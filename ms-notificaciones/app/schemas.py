"""
ESQUEMAS (DTO) del microservicio de notificaciones.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import EstadoEnvio


class SolicitudMedicaNotificar(BaseModel):
    """
    Datos que envia la aplicacion base cuando el medico general crea una
    solicitud de referencia a especialidad.
    """

    paciente_id: int = Field(gt=0)
    paciente_nombre: str = Field(min_length=3, max_length=120)
    familiar_nombre: str = Field(min_length=3, max_length=120)
    correo_destino: EmailStr
    especialidad: str = Field(min_length=3, max_length=80)
    medico_asignado: str = Field(min_length=3, max_length=120)
    motivo: str = Field(min_length=3, max_length=300)
    estado_paciente: str = Field(default="Estable", max_length=80)


class NotificacionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paciente_id: int
    paciente_nombre: str
    familiar_nombre: str
    correo_destino: str
    asunto: str
    mensaje: str
    estado: EstadoEnvio
    detalle_error: Optional[str]
    fecha_envio: datetime
