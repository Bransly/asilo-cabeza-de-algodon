"""
CAPA DE ACCESO A DATOS  (patron Repositorio)

Unica capa autorizada a consultar la base de datos, tal como se definio en el
documento "Estructura de Capas del Proyecto". La capa de negocio nunca escribe
SQL ni conoce SQLAlchemy: solo llama estos metodos.
"""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from models import (
    Enfermero, Especialidad, EstadoExamen, EstadoSolicitud, EstadoVisita,
    FichaMedica, Medico, MedicamentoPermanente, MedicamentoRecetado,
    OrdenExamen, Paciente, RegistroBitacora, Solicitud, Usuario, VisitaMedica,
)


class RepositorioBase:
    def __init__(self, sesion: Session):
        self.sesion = sesion

    def guardar(self, entidad):
        self.sesion.add(entidad)
        self.sesion.commit()
        self.sesion.refresh(entidad)
        return entidad

    def confirmar(self):
        self.sesion.commit()


class PacienteRepository(RepositorioBase):
    def listar(self, solo_activos: bool = True):
        consulta = select(Paciente).options(selectinload(Paciente.ficha))
        if solo_activos:
            consulta = consulta.where(Paciente.activo.is_(True))
        return list(self.sesion.scalars(consulta.order_by(Paciente.nombre)))

    def obtener(self, paciente_id: int):
        consulta = (
            select(Paciente)
            .options(
                selectinload(Paciente.ficha),
                selectinload(Paciente.medicamentos_permanentes),
                selectinload(Paciente.solicitudes).selectinload(Solicitud.especialidad),
                selectinload(Paciente.solicitudes).selectinload(Solicitud.medico),
                selectinload(Paciente.solicitudes).selectinload(Solicitud.enfermero),
                selectinload(Paciente.visitas).selectinload(VisitaMedica.medico),
                selectinload(Paciente.visitas).selectinload(VisitaMedica.examenes),
                selectinload(Paciente.visitas).selectinload(VisitaMedica.recetas),
            )
            .where(Paciente.id == paciente_id)
        )
        return self.sesion.scalars(consulta).first()

    def contar(self) -> int:
        return self.sesion.scalar(
            select(func.count()).select_from(Paciente).where(Paciente.activo.is_(True))
        ) or 0

    def eliminar(self, paciente: Paciente):
        """Baja logica: el expediente clinico nunca se borra fisicamente."""
        paciente.activo = False
        self.confirmar()


class FichaRepository(RepositorioBase):
    def obtener_por_paciente(self, paciente_id: int):
        return self.sesion.scalars(
            select(FichaMedica).where(FichaMedica.paciente_id == paciente_id)
        ).first()


class MedicamentoPermanenteRepository(RepositorioBase):
    def obtener(self, medicamento_id: int):
        return self.sesion.get(MedicamentoPermanente, medicamento_id)

    def eliminar(self, medicamento: MedicamentoPermanente):
        self.sesion.delete(medicamento)
        self.confirmar()


class CatalogoRepository(RepositorioBase):
    """Especialidades, medicos y enfermeros que aporta la fundacion."""

    def especialidades(self):
        return list(self.sesion.scalars(select(Especialidad).order_by(Especialidad.nombre)))

    def medicos(self, especialidad_id: int | None = None):
        consulta = select(Medico).options(selectinload(Medico.especialidad))
        if especialidad_id:
            consulta = consulta.where(Medico.especialidad_id == especialidad_id)
        return list(self.sesion.scalars(consulta.order_by(Medico.nombre)))

    def enfermeros(self):
        return list(self.sesion.scalars(select(Enfermero).order_by(Enfermero.nombre)))


class SolicitudRepository(RepositorioBase):
    def obtener(self, solicitud_id: int):
        consulta = (
            select(Solicitud)
            .options(
                selectinload(Solicitud.paciente),
                selectinload(Solicitud.especialidad),
                selectinload(Solicitud.medico),
                selectinload(Solicitud.enfermero),
                selectinload(Solicitud.visita),
            )
            .where(Solicitud.id == solicitud_id)
        )
        return self.sesion.scalars(consulta).first()

    def listar(self, estado: EstadoSolicitud | None = None):
        consulta = select(Solicitud).options(
            selectinload(Solicitud.paciente),
            selectinload(Solicitud.especialidad),
            selectinload(Solicitud.medico),
            selectinload(Solicitud.enfermero),
            selectinload(Solicitud.visita),
        )
        if estado:
            consulta = consulta.where(Solicitud.estado == estado)
        return list(self.sesion.scalars(consulta.order_by(Solicitud.fecha_creacion.desc())))

    def contar_pendientes(self) -> int:
        return self.sesion.scalar(
            select(func.count()).select_from(Solicitud)
            .where(Solicitud.estado == EstadoSolicitud.PENDIENTE)
        ) or 0


class VisitaRepository(RepositorioBase):
    def obtener(self, visita_id: int):
        consulta = (
            select(VisitaMedica)
            .options(
                selectinload(VisitaMedica.paciente).selectinload(Paciente.ficha),
                selectinload(VisitaMedica.paciente)
                .selectinload(Paciente.medicamentos_permanentes),
                selectinload(VisitaMedica.medico).selectinload(Medico.especialidad),
                selectinload(VisitaMedica.solicitud).selectinload(Solicitud.enfermero),
                selectinload(VisitaMedica.examenes),
                selectinload(VisitaMedica.recetas),
            )
            .where(VisitaMedica.id == visita_id)
        )
        return self.sesion.scalars(consulta).first()

    def historial(self, paciente_id: int):
        """Historial medico del interno, de la visita mas reciente a la mas antigua."""
        consulta = (
            select(VisitaMedica)
            .options(
                selectinload(VisitaMedica.medico).selectinload(Medico.especialidad),
                selectinload(VisitaMedica.examenes),
                selectinload(VisitaMedica.recetas),
            )
            .where(VisitaMedica.paciente_id == paciente_id)
            .order_by(VisitaMedica.fecha.desc())
        )
        return list(self.sesion.scalars(consulta))

    def contar_abiertas(self) -> int:
        return self.sesion.scalar(
            select(func.count()).select_from(VisitaMedica)
            .where(VisitaMedica.estado == EstadoVisita.ABIERTA)
        ) or 0


class ExamenRepository(RepositorioBase):
    def obtener(self, examen_id: int):
        consulta = (
            select(OrdenExamen)
            .options(
                selectinload(OrdenExamen.visita).selectinload(VisitaMedica.paciente),
                selectinload(OrdenExamen.visita).selectinload(VisitaMedica.medico),
            )
            .where(OrdenExamen.id == examen_id)
        )
        return self.sesion.scalars(consulta).first()

    def pendientes_de_resultado(self):
        consulta = (
            select(OrdenExamen)
            .options(
                selectinload(OrdenExamen.visita).selectinload(VisitaMedica.paciente),
                selectinload(OrdenExamen.visita).selectinload(VisitaMedica.medico),
            )
            .where(OrdenExamen.estado == EstadoExamen.SOLICITADO)
            .order_by(OrdenExamen.fecha_solicitud)
        )
        return list(self.sesion.scalars(consulta))

    def con_resultado(self, limite: int = 20):
        consulta = (
            select(OrdenExamen)
            .options(selectinload(OrdenExamen.visita).selectinload(VisitaMedica.paciente))
            .where(OrdenExamen.estado == EstadoExamen.CON_RESULTADO)
            .order_by(OrdenExamen.fecha_resultado.desc())
            .limit(limite)
        )
        return list(self.sesion.scalars(consulta))

    def contar_pendientes(self) -> int:
        return self.sesion.scalar(
            select(func.count()).select_from(OrdenExamen)
            .where(OrdenExamen.estado == EstadoExamen.SOLICITADO)
        ) or 0


class RecetaRepository(RepositorioBase):
    def obtener(self, receta_id: int):
        consulta = (
            select(MedicamentoRecetado)
            .options(
                selectinload(MedicamentoRecetado.visita).selectinload(VisitaMedica.paciente),
                selectinload(MedicamentoRecetado.visita).selectinload(VisitaMedica.medico),
            )
            .where(MedicamentoRecetado.id == receta_id)
        )
        return self.sesion.scalars(consulta).first()

    def pendientes_de_entrega(self):
        consulta = (
            select(MedicamentoRecetado)
            .options(
                selectinload(MedicamentoRecetado.visita).selectinload(VisitaMedica.paciente),
                selectinload(MedicamentoRecetado.visita).selectinload(VisitaMedica.medico),
            )
            .where(MedicamentoRecetado.entregado.is_(False))
            .order_by(MedicamentoRecetado.fecha_receta)
        )
        return list(self.sesion.scalars(consulta))

    def entregadas(self, limite: int = 20):
        consulta = (
            select(MedicamentoRecetado)
            .options(selectinload(MedicamentoRecetado.visita)
                     .selectinload(VisitaMedica.paciente))
            .where(MedicamentoRecetado.entregado.is_(True))
            .order_by(MedicamentoRecetado.fecha_entrega.desc())
            .limit(limite)
        )
        return list(self.sesion.scalars(consulta))

    def contar_pendientes(self) -> int:
        return self.sesion.scalar(
            select(func.count()).select_from(MedicamentoRecetado)
            .where(MedicamentoRecetado.entregado.is_(False))
        ) or 0


def marcar_actualizada(ficha: FichaMedica) -> None:
    ficha.actualizada = datetime.now()


class UsuarioRepository(RepositorioBase):
    """Acceso a credenciales. Nunca devuelve ni registra contrasenas en claro."""

    def obtener_por_nombre(self, nombre_usuario: str):
        return self.sesion.scalars(
            select(Usuario).where(Usuario.usuario == nombre_usuario)
        ).first()

    def obtener(self, usuario_id: int):
        return self.sesion.get(Usuario, usuario_id)

    def listar(self):
        return list(self.sesion.scalars(select(Usuario).order_by(Usuario.nombre)))


class BitacoraRepository(RepositorioBase):
    def ultimos(self, limite: int = 100):
        return list(self.sesion.scalars(
            select(RegistroBitacora).order_by(RegistroBitacora.fecha.desc()).limit(limite)
        ))
