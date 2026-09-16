"""
CAPA DE ACCESO A DATOS - Patron Repositorio
Unica capa autorizada a ejecutar consultas. Devuelve objetos de la capa de
entidades, nunca filas crudas. Usa el ORM con consultas parametrizadas para
evitar inyeccion SQL, tal como se definio en el documento de capas.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import Cargo, EstadoCargo, Tarifa


class TarifaRepository:
    def __init__(self, db: Session):
        self.db = db

    def listar(self, solo_activas: bool = False) -> List[Tarifa]:
        consulta = self.db.query(Tarifa)
        if solo_activas:
            consulta = consulta.filter(Tarifa.activo.is_(True))
        return consulta.order_by(Tarifa.tipo_servicio, Tarifa.descripcion).all()

    def obtener(self, tarifa_id: int) -> Optional[Tarifa]:
        return self.db.query(Tarifa).filter(Tarifa.id == tarifa_id).first()

    def crear(self, tarifa: Tarifa) -> Tarifa:
        self.db.add(tarifa)
        self.db.commit()
        self.db.refresh(tarifa)
        return tarifa

    def actualizar(self, tarifa: Tarifa) -> Tarifa:
        self.db.commit()
        self.db.refresh(tarifa)
        return tarifa

    def eliminar(self, tarifa: Tarifa) -> None:
        self.db.delete(tarifa)
        self.db.commit()

    def contar(self) -> int:
        return self.db.query(Tarifa).count()


class CargoRepository:
    def __init__(self, db: Session):
        self.db = db

    def listar(
        self,
        paciente_id: Optional[int] = None,
        estado: Optional[EstadoCargo] = None,
    ) -> List[Cargo]:
        consulta = self.db.query(Cargo)
        if paciente_id is not None:
            consulta = consulta.filter(Cargo.paciente_id == paciente_id)
        if estado is not None:
            consulta = consulta.filter(Cargo.estado == estado)
        return consulta.order_by(Cargo.fecha_registro.desc()).all()

    def obtener(self, cargo_id: int) -> Optional[Cargo]:
        return self.db.query(Cargo).filter(Cargo.id == cargo_id).first()

    def crear(self, cargo: Cargo) -> Cargo:
        self.db.add(cargo)
        self.db.commit()
        self.db.refresh(cargo)
        return cargo

    def guardar(self, cargo: Cargo) -> Cargo:
        self.db.commit()
        self.db.refresh(cargo)
        return cargo

    def eliminar(self, cargo: Cargo) -> None:
        self.db.delete(cargo)
        self.db.commit()
