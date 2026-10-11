from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from .models import EstadoEnvio, TipoAviso


class SolicitudMedicaNotificar(BaseModel):
    tipo: TipoAviso = TipoAviso.SOLICITUD_REGISTRADA
    solicitud_id: Optional[int] = Field(default=None, gt=0)
    paciente_id: int = Field(gt=0)
    paciente_nombre: str = Field(min_length=3, max_length=120)
    familiar_nombre: str = Field(min_length=3, max_length=120)
    correo_destino: EmailStr
    especialidad: str = Field(min_length=3, max_length=80)
    # El medico existe solo cuando la fundacion lo asigna (aviso MEDICO_ASIGNADO).
    medico_asignado: Optional[str] = Field(default=None, min_length=3, max_length=120)
    fecha_cita: Optional[datetime] = None
    motivo: str = Field(min_length=3, max_length=300)
    estado_paciente: str = Field(default="Estable", max_length=80)

    @model_validator(mode="after")
    def medico_obligatorio_al_asignar(self):
        if self.tipo == TipoAviso.MEDICO_ASIGNADO and not (
                self.medico_asignado and self.fecha_cita):
            raise ValueError("El aviso de asignación requiere el médico y la fecha de la cita")
        return self


class NotificacionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoAviso
    solicitud_id: Optional[int]
    paciente_id: int
    paciente_nombre: str
    familiar_nombre: str
    correo_destino: str
    asunto: str
    mensaje: str
    estado: EstadoEnvio
    detalle_error: Optional[str]
    fecha_envio: datetime
