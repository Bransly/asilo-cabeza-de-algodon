"""
CAPA DE ACCESO A DATOS - Patron Repositorio
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import EstadoEnvio, Notificacion


class NotificacionRepository:
    def __init__(self, db: Session):
        self.db = db

    def listar(
        self,
        paciente_id: Optional[int] = None,
        estado: Optional[EstadoEnvio] = None,
        limite: int = 50,
    ) -> List[Notificacion]:
        consulta = self.db.query(Notificacion)
        if paciente_id is not None:
            consulta = consulta.filter(Notificacion.paciente_id == paciente_id)
        if estado is not None:
            consulta = consulta.filter(Notificacion.estado == estado)
        return consulta.order_by(Notificacion.fecha_envio.desc()).limit(limite).all()

    def obtener(self, notificacion_id: int) -> Optional[Notificacion]:
        return self.db.query(Notificacion).filter(Notificacion.id == notificacion_id).first()

    def crear(self, notificacion: Notificacion) -> Notificacion:
        self.db.add(notificacion)
        self.db.commit()
        self.db.refresh(notificacion)
        return notificacion

    def eliminar(self, notificacion: Notificacion) -> None:
        self.db.delete(notificacion)
        self.db.commit()
