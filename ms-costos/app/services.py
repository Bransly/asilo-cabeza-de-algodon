"""
CAPA DE LOGICA DE NEGOCIO
Aqui viven las reglas del asilo. Esta capa no sabe nada de HTTP ni de SQL:
recibe datos, aplica reglas y delega la persistencia al repositorio.

Regla principal implementada (enunciado del proyecto):
"El costo de la cita, de los examenes de laboratorio y de farmacia son cargados
a la cuenta del familiar siempre con el descuento que proporciona la fundacion."
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from .models import Cargo, EstadoCargo, Tarifa, TipoServicio
from .repository import CargoRepository, TarifaRepository
from .schemas import CargoCrear, EstadoCuenta, TarifaActualizar, TarifaCrear


class ReglaNegocioError(Exception):
    """Error de negocio. La capa de presentacion lo traduce a HTTP 400/404."""

    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def _redondear(valor: float) -> float:
    return round(valor + 1e-9, 2)


class TarifaService:
    def __init__(self, db: Session):
        self.repo = TarifaRepository(db)

    def listar(self, solo_activas: bool = False) -> List[Tarifa]:
        return self.repo.listar(solo_activas)

    def obtener(self, tarifa_id: int) -> Tarifa:
        tarifa = self.repo.obtener(tarifa_id)
        if tarifa is None:
            raise ReglaNegocioError(f"No existe la tarifa {tarifa_id}", 404)
        return tarifa

    def crear(self, datos: TarifaCrear) -> Tarifa:
        return self.repo.crear(Tarifa(**datos.model_dump()))

    def actualizar(self, tarifa_id: int, datos: TarifaActualizar) -> Tarifa:
        tarifa = self.obtener(tarifa_id)
        for campo, valor in datos.model_dump(exclude_unset=True).items():
            setattr(tarifa, campo, valor)
        return self.repo.actualizar(tarifa)

    def eliminar(self, tarifa_id: int) -> None:
        self.repo.eliminar(self.obtener(tarifa_id))

    def sembrar_catalogo_inicial(self) -> None:
        """Carga tarifas de ejemplo la primera vez, para poder demostrar el sistema."""
        if self.repo.contar() > 0:
            return
        catalogo = [
            (TipoServicio.CONSULTA, "Consulta con medico general", 150.00, 40.0),
            (TipoServicio.CONSULTA, "Consulta con especialista", 350.00, 35.0),
            (TipoServicio.EXAMEN, "Hematologia completa", 120.00, 50.0),
            (TipoServicio.EXAMEN, "Perfil lipidico", 200.00, 45.0),
            (TipoServicio.EXAMEN, "Glucosa en ayunas", 60.00, 50.0),
            (TipoServicio.MEDICAMENTO, "Losartan 50mg (tableta)", 3.50, 30.0),
            (TipoServicio.MEDICAMENTO, "Metformina 850mg (tableta)", 2.75, 30.0),
        ]
        for tipo, descripcion, precio, descuento in catalogo:
            self.repo.crear(
                Tarifa(
                    tipo_servicio=tipo,
                    descripcion=descripcion,
                    precio_base=precio,
                    descuento_fundacion=descuento,
                    activo=True,
                )
            )
        print("[ms-costos] Catalogo de tarifas inicial cargado")


class CargoService:
    def __init__(self, db: Session):
        self.repo = CargoRepository(db)
        self.tarifas = TarifaService(db)

    def registrar(self, datos: CargoCrear) -> Cargo:
        """Calcula el cargo aplicando el descuento de la fundacion."""
        tarifa = self.tarifas.obtener(datos.tarifa_id)

        # Regla: no se puede cobrar con una tarifa dada de baja.
        if not tarifa.activo:
            raise ReglaNegocioError("La tarifa esta inactiva y no puede cobrarse")

        subtotal = tarifa.precio_base * datos.cantidad
        total = subtotal * (1 - tarifa.descuento_fundacion / 100)

        cargo = Cargo(
            paciente_id=datos.paciente_id,
            paciente_nombre=datos.paciente_nombre.strip(),
            visita_id=datos.visita_id,
            tarifa_id=tarifa.id,
            tipo_servicio=tarifa.tipo_servicio,
            descripcion=tarifa.descripcion,
            cantidad=datos.cantidad,
            precio_base=tarifa.precio_base,
            descuento_aplicado=tarifa.descuento_fundacion,
            subtotal=_redondear(subtotal),
            total=_redondear(total),
            estado=EstadoCargo.PENDIENTE,
        )
        return self.repo.crear(cargo)

    def listar(self, paciente_id: Optional[int], estado: Optional[EstadoCargo]) -> List[Cargo]:
        return self.repo.listar(paciente_id, estado)

    def obtener(self, cargo_id: int) -> Cargo:
        cargo = self.repo.obtener(cargo_id)
        if cargo is None:
            raise ReglaNegocioError(f"No existe el cargo {cargo_id}", 404)
        return cargo

    def marcar_pagado(self, cargo_id: int) -> Cargo:
        cargo = self.obtener(cargo_id)
        # Regla: un cargo ya cancelado no se vuelve a cobrar.
        if cargo.estado == EstadoCargo.PAGADO:
            raise ReglaNegocioError("El cargo ya estaba cancelado")
        cargo.estado = EstadoCargo.PAGADO
        return self.repo.guardar(cargo)

    def eliminar(self, cargo_id: int) -> None:
        cargo = self.obtener(cargo_id)
        # Regla: no se borra historial de lo que ya se cobro.
        if cargo.estado == EstadoCargo.PAGADO:
            raise ReglaNegocioError("No se puede eliminar un cargo ya pagado")
        self.repo.eliminar(cargo)

    def estado_cuenta(self, paciente_id: int) -> EstadoCuenta:
        """Reporte de cobros por paciente (requerido en el modulo de reportes)."""
        cargos = self.repo.listar(paciente_id=paciente_id)
        if not cargos:
            raise ReglaNegocioError(f"El paciente {paciente_id} no tiene cargos registrados", 404)

        sin_descuento = sum(c.subtotal for c in cargos)
        facturado = sum(c.total for c in cargos)
        pagado = sum(c.total for c in cargos if c.estado == EstadoCargo.PAGADO)

        return EstadoCuenta(
            paciente_id=paciente_id,
            paciente_nombre=cargos[0].paciente_nombre,
            cantidad_cargos=len(cargos),
            total_sin_descuento=_redondear(sin_descuento),
            total_ahorrado=_redondear(sin_descuento - facturado),
            total_facturado=_redondear(facturado),
            total_pagado=_redondear(pagado),
            saldo_pendiente=_redondear(facturado - pagado),
        )
