"""Sin credenciales SMTP el correo se registra como SIMULADA, sin enviarse."""
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from .models import EstadoEnvio, Notificacion, TipoAviso
from .repository import NotificacionRepository
from .schemas import SolicitudMedicaNotificar

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
CORREO_REMITENTE = os.getenv("CORREO_REMITENTE", "asilo.cabezadealgodon@ejemplo.com")


class ReglaNegocioError(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


class NotificacionService:
    def __init__(self, db: Session):
        self.repo = NotificacionRepository(db)

    def _redactar(self, datos: SolicitudMedicaNotificar) -> Tuple[str, str]:
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        saludo = f"Estimado(a) {datos.familiar_nombre}:\n\n"
        firma = "Atentamente,\nAsilo de Ancianos Cabeza de Algodón"

        if datos.tipo == TipoAviso.MEDICO_ASIGNADO:
            asunto = f"Médico asignado - {datos.paciente_nombre}"
            cita = datos.fecha_cita.strftime("%d/%m/%Y a las %H:%M")
            cuerpo = (
                f"La fundación asignó el médico que atenderá a su familiar "
                f"{datos.paciente_nombre}.\n\n"
                f"Médico asignado: {datos.medico_asignado}\n"
                f"Especialidad: {datos.especialidad}\n"
                f"Fecha de la cita: {cita}\n"
                f"Motivo de la referencia: {datos.motivo}\n"
                f"Estado actual del paciente: {datos.estado_paciente}\n\n"
                f"Un enfermero(a) del asilo acompañará a su familiar a la cita.\n\n"
            )
        else:
            asunto = f"Solicitud médica registrada - {datos.paciente_nombre}"
            cuerpo = (
                f"Le informamos que el día {fecha} el médico general del asilo refirió a "
                f"su familiar {datos.paciente_nombre} a una consulta especializada.\n\n"
                f"Especialidad a la que fue referido: {datos.especialidad}\n"
                f"Motivo de la referencia: {datos.motivo}\n"
                f"Estado actual del paciente: {datos.estado_paciente}\n\n"
                f"La fundación asignará el médico y el horario de la cita. Recibirá otro "
                f"correo con el nombre del médico en cuanto quede asignado.\n\n"
            )
        return asunto, saludo + cuerpo + firma

    def _enviar_correo(self, destino: str, asunto: str, cuerpo: str) -> Tuple[EstadoEnvio, Optional[str]]:
        if not SMTP_HOST or not SMTP_USUARIO:
            print(f"[ms-notificaciones] MODO SIMULADO -> {destino} | {asunto}")
            return EstadoEnvio.SIMULADA, None

        try:
            correo = EmailMessage()
            correo["From"] = CORREO_REMITENTE
            correo["To"] = destino
            correo["Subject"] = asunto
            correo.set_content(cuerpo)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as servidor:
                servidor.starttls()
                servidor.login(SMTP_USUARIO, SMTP_PASSWORD)
                servidor.send_message(correo)

            return EstadoEnvio.ENVIADA, None
        except Exception as error:
            return EstadoEnvio.FALLIDA, str(error)[:250]

    def notificar_solicitud(self, datos: SolicitudMedicaNotificar) -> Notificacion:
        asunto, mensaje = self._redactar(datos)
        estado, detalle = self._enviar_correo(datos.correo_destino, asunto, mensaje)

        notificacion = Notificacion(
            tipo=datos.tipo,
            solicitud_id=datos.solicitud_id,
            paciente_id=datos.paciente_id,
            paciente_nombre=datos.paciente_nombre.strip(),
            familiar_nombre=datos.familiar_nombre.strip(),
            correo_destino=str(datos.correo_destino),
            asunto=asunto,
            mensaje=mensaje,
            estado=estado,
            detalle_error=detalle,
        )
        return self.repo.crear(notificacion)

    def listar(self, paciente_id: Optional[int], estado: Optional[EstadoEnvio]) -> List[Notificacion]:
        return self.repo.listar(paciente_id, estado)

    def obtener(self, notificacion_id: int) -> Notificacion:
        notificacion = self.repo.obtener(notificacion_id)
        if notificacion is None:
            raise ReglaNegocioError(f"No existe la notificación {notificacion_id}", 404)
        return notificacion

    def reenviar(self, notificacion_id: int) -> Notificacion:
        """Vuelve a intentar un envio fallido y deja el nuevo registro en bitacora."""
        original = self.obtener(notificacion_id)
        estado, detalle = self._enviar_correo(
            original.correo_destino, original.asunto, original.mensaje
        )
        copia = Notificacion(
            tipo=original.tipo,
            solicitud_id=original.solicitud_id,
            paciente_id=original.paciente_id,
            paciente_nombre=original.paciente_nombre,
            familiar_nombre=original.familiar_nombre,
            correo_destino=original.correo_destino,
            asunto=original.asunto,
            mensaje=original.mensaje,
            estado=estado,
            detalle_error=detalle,
        )
        return self.repo.crear(copia)

    def eliminar(self, notificacion_id: int) -> None:
        self.repo.eliminar(self.obtener(notificacion_id))
