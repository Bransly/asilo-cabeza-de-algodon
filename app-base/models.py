"""
CAPA DE ENTIDADES / MODELOS  (aplicacion base)

Clases del dominio clinico del asilo, tomadas del ERD documentado en la fase
de analisis. No contienen reglas de negocio: solo estructura y relaciones.

Los cobros NO estan aqui: viven en el microservicio ms-costos. La aplicacion
base guarda unicamente el identificador del cargo que ese servicio devolvio.
"""
import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class EstadoSolicitud(str, enum.Enum):
    PENDIENTE = "PENDIENTE"    # creada por el medico general
    ASIGNADA = "ASIGNADA"      # la fundacion asigno medico y horario
    ATENDIDA = "ATENDIDA"      # se convirtio en visita medica


class EstadoVisita(str, enum.Enum):
    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"


class EstadoExamen(str, enum.Enum):
    SOLICITADO = "SOLICITADO"
    CON_RESULTADO = "CON_RESULTADO"


# --------------------------------------------------------------- Paciente
class Paciente(Base):
    """Interno del asilo."""

    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    edad: Mapped[int] = mapped_column(Integer, nullable=False)
    fecha_ingreso: Mapped[date] = mapped_column(Date, default=date.today)
    motivo_ingreso: Mapped[str] = mapped_column(String(300), default="")

    familiar_nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    correo_familiar: Mapped[str] = mapped_column(String(150), nullable=False)
    telefono_familiar: Mapped[str] = mapped_column(String(30), default="")
    cuota_mensual: Mapped[float] = mapped_column(Float, default=0.0)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    ficha: Mapped["FichaMedica"] = relationship(
        back_populates="paciente", uselist=False, cascade="all, delete-orphan")
    medicamentos_permanentes: Mapped[list["MedicamentoPermanente"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan")
    solicitudes: Mapped[list["Solicitud"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan")
    visitas: Mapped[list["VisitaMedica"]] = relationship(
        back_populates="paciente", cascade="all, delete-orphan")


class FichaMedica(Base):
    """
    Ficha clinica del interno. Agrupa psicopatologia y padecimientos, tal como
    lo pide el enunciado: "permite ver los padecimientos y enfermedades que
    cada uno ha presentado".
    """

    __tablename__ = "fichas_medicas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"), unique=True)

    psicopatologia: Mapped[str] = mapped_column(Text, default="")
    padecimientos: Mapped[str] = mapped_column(Text, default="")
    alergias: Mapped[str] = mapped_column(Text, default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    actualizada: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    paciente: Mapped["Paciente"] = relationship(back_populates="ficha")


class MedicamentoPermanente(Base):
    """Las "medicinas de cajon" que el interno recibe de forma continua."""

    __tablename__ = "medicamentos_permanentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    dosis: Mapped[str] = mapped_column(String(80), default="")
    frecuencia: Mapped[str] = mapped_column(String(80), default="")

    paciente: Mapped["Paciente"] = relationship(back_populates="medicamentos_permanentes")


# ------------------------------------------------- Personal de la fundacion
class Especialidad(Base):
    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)

    medicos: Mapped[list["Medico"]] = relationship(back_populates="especialidad")


class Medico(Base):
    __tablename__ = "medicos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    colegiado: Mapped[str] = mapped_column(String(30), default="")
    especialidad_id: Mapped[int] = mapped_column(ForeignKey("especialidades.id"))

    especialidad: Mapped["Especialidad"] = relationship(back_populates="medicos")


class Enfermero(Base):
    """Personal que acompania al paciente durante la atencion."""

    __tablename__ = "enfermeros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    turno: Mapped[str] = mapped_column(String(40), default="Matutino")


# ------------------------------------------------------ Flujo de atencion
class Solicitud(Base):
    """
    Referencia que hace el medico general hacia una especialidad. Aparece en el
    modulo de la fundacion, que asigna medico y horario.
    """

    __tablename__ = "solicitudes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    especialidad_id: Mapped[int] = mapped_column(ForeignKey("especialidades.id"))
    enfermero_id: Mapped[int | None] = mapped_column(ForeignKey("enfermeros.id"), nullable=True)
    medico_id: Mapped[int | None] = mapped_column(ForeignKey("medicos.id"), nullable=True)

    motivo: Mapped[str] = mapped_column(String(300), nullable=False)
    estado_paciente: Mapped[str] = mapped_column(String(80), default="Estable")
    estado: Mapped[EstadoSolicitud] = mapped_column(
        Enum(EstadoSolicitud), default=EstadoSolicitud.PENDIENTE)

    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_asignada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    paciente: Mapped["Paciente"] = relationship(back_populates="solicitudes")
    especialidad: Mapped["Especialidad"] = relationship()
    enfermero: Mapped["Enfermero"] = relationship()
    medico: Mapped["Medico"] = relationship()
    visita: Mapped["VisitaMedica"] = relationship(back_populates="solicitud", uselist=False)


class VisitaMedica(Base):
    """
    La solicitud atendida se convierte en visita medica. Concentra los datos
    que el enunciado exige para la ficha: fecha, motivo, medico tratante,
    examenes, resultados, diagnostico, medicamentos y observaciones.
    """

    __tablename__ = "visitas_medicas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"), unique=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("medicos.id"))

    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    motivo: Mapped[str] = mapped_column(String(300), default="")
    diagnostico: Mapped[str] = mapped_column(Text, default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[EstadoVisita] = mapped_column(Enum(EstadoVisita), default=EstadoVisita.ABIERTA)

    cargo_consulta_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    paciente: Mapped["Paciente"] = relationship(back_populates="visitas")
    medico: Mapped["Medico"] = relationship()
    solicitud: Mapped["Solicitud"] = relationship(back_populates="visita")
    examenes: Mapped[list["OrdenExamen"]] = relationship(
        back_populates="visita", cascade="all, delete-orphan")
    recetas: Mapped[list["MedicamentoRecetado"]] = relationship(
        back_populates="visita", cascade="all, delete-orphan")


class OrdenExamen(Base):
    """Examen de laboratorio solicitado dentro de una visita medica."""

    __tablename__ = "ordenes_examen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visita_id: Mapped[int] = mapped_column(ForeignKey("visitas_medicas.id"))

    tarifa_id: Mapped[int] = mapped_column(Integer, nullable=False)   # catalogo de ms-costos
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    indicaciones: Mapped[str] = mapped_column(String(300), default="")

    estado: Mapped[EstadoExamen] = mapped_column(
        Enum(EstadoExamen), default=EstadoExamen.SOLICITADO)
    resultado: Mapped[str] = mapped_column(Text, default="")
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_resultado: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cargo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    visita: Mapped["VisitaMedica"] = relationship(back_populates="examenes")


class MedicamentoRecetado(Base):
    """Medicamento indicado por el medico y entregado por la farmacia."""

    __tablename__ = "medicamentos_recetados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visita_id: Mapped[int] = mapped_column(ForeignKey("visitas_medicas.id"))

    tarifa_id: Mapped[int] = mapped_column(Integer, nullable=False)   # catalogo de ms-costos
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, default=1)
    indicaciones: Mapped[str] = mapped_column(String(300), default="")

    entregado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_receta: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    fecha_entrega: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cargo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    visita: Mapped["VisitaMedica"] = relationship(back_populates="recetas")


# ------------------------------------------------------------- Seguridad
class RolUsuario(str, enum.Enum):
    """Roles definidos en la matriz del Documento de Diseno Arquitectonico."""

    ADMINISTRADOR = "ADMINISTRADOR"
    MEDICO_GENERAL = "MEDICO_GENERAL"
    MEDICO_ESPECIALISTA = "MEDICO_ESPECIALISTA"
    ENFERMERIA = "ENFERMERIA"
    LABORATORIO = "LABORATORIO"
    FARMACIA = "FARMACIA"
    CAJA = "CAJA"
    FUNDACION = "FUNDACION"


ETIQUETA_ROL = {
    RolUsuario.ADMINISTRADOR: "Administrador",
    RolUsuario.MEDICO_GENERAL: "Medico general",
    RolUsuario.MEDICO_ESPECIALISTA: "Medico especialista",
    RolUsuario.ENFERMERIA: "Enfermeria",
    RolUsuario.LABORATORIO: "Laboratorio",
    RolUsuario.FARMACIA: "Farmacia",
    RolUsuario.CAJA: "Caja",
    RolUsuario.FUNDACION: "Fundacion",
}


class Usuario(Base):
    """
    Credenciales y rol del personal del asilo y de la fundacion.
    La contrasena se guarda unicamente como hash con sal (scrypt).
    """

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    usuario: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    hash_contrasena: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(Enum(RolUsuario), nullable=False)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RegistroBitacora(Base):
    """
    Bitacora de auditoria. Responde quien hizo que, cuando, sobre que entidad y
    con que resultado, tal como exige el documento de arquitectura.
    """

    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usuario_nombre: Mapped[str] = mapped_column(String(120), default="anonimo")
    rol: Mapped[str] = mapped_column(String(40), default="-")

    accion: Mapped[str] = mapped_column(String(60), nullable=False)
    entidad: Mapped[str] = mapped_column(String(60), default="")
    entidad_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resultado: Mapped[str] = mapped_column(String(20), default="EXITO")
    detalle: Mapped[str] = mapped_column(String(300), default="")
    direccion_ip: Mapped[str] = mapped_column(String(45), default="")
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
