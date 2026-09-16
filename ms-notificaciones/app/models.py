"""
CAPA DE ENTIDADES / MODELOS
La notificacion se guarda siempre, aunque el correo falle. Esa bitacora es la
evidencia de que se informo al familiar y sirve para la auditoria del sistema.
"""
import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text

from .database import Base


class EstadoEnvio(str, enum.Enum):
    ENVIADA = "ENVIADA"      # el servidor SMTP acepto el correo
    SIMULADA = "SIMULADA"    # no hay SMTP configurado, se registro sin enviar
    FALLIDA = "FALLIDA"      # hubo error al enviar


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)

    paciente_id = Column(Integer, nullable=False, index=True)
    paciente_nombre = Column(String(120), nullable=False)
    familiar_nombre = Column(String(120), nullable=False)
    correo_destino = Column(String(150), nullable=False)

    asunto = Column(String(180), nullable=False)
    mensaje = Column(Text, nullable=False)

    estado = Column(Enum(EstadoEnvio), nullable=False, default=EstadoEnvio.SIMULADA)
    detalle_error = Column(String(255), nullable=True)
    fecha_envio = Column(DateTime, nullable=False, default=datetime.utcnow)
