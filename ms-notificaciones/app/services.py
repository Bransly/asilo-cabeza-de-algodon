"""
CAPA DE LOGICA DE NEGOCIO
Requerimiento del enunciado:
"El sistema debera enviar un correo electronico al familiar del paciente cuando
se crea una solicitud para un medico, informando el estado del paciente y a que
medico fue referido."

Si no hay credenciales SMTP configuradas, el correo se registra en modo SIMULADA.
Asi el sistema puede demostrarse sin depender de un servidor de correo real.
"""
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

    # ---------------- Redaccion del mensaje ----------------
    def _redactar(self, datos: SolicitudMedicaNotificar) -> Tuple[str, str]:
        """
        Dos avisos cumplen juntos el requisito del enunciado ("informando el
        estado del paciente y a que medico fue referido"):
          - SOLICITUD_REGISTRADA: especialidad, motivo y estado del paciente.
          - MEDICO_ASIGNADO: nombre del medico y fecha y hora de la cita.
        """
        fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
        saludo = f"Estimado(a) {datos.familiar_nombre}:\n\n"
        firma = "Atentamente,\nAsilo de Ancianos Cabeza de Algodon"

        if datos.tipo == TipoAviso.MEDICO_ASIGNADO:
            asunto = f"Medico asignado - {datos.paciente_nombre}"
            cita = datos.fecha_cita.strftime("%d/%m/%Y a las %H:%M")
            cuerpo = (
                f"La fundacion asigno el medico que atendera a su familiar "
                f"{datos.paciente_nombre}.\n\n"
                f"Medico asignado: {datos.medico_asignado}\n"
                f"Especialidad: {datos.especialidad}\n"
                f"Fecha de la cita: {cita}\n"
                f"Motivo de la referencia: {datos.motivo}\n"
                f"Estado actual del paciente: {datos.estado_paciente}\n\n"
                f"Un enfermero(a) del asilo acompanara a su familiar a la cita.\n\n"
            )
        else:
            asunto = f"Solicitud medica registrada - {datos.paciente_nombre}"
            cuerpo = (
                f"Le informamos que el dia {fecha} el medico general del asilo refirio a "
                f"su familiar {datos.paciente_nombre} a una consulta especializada.\n\n"
                f"Especialidad a la que fue referido: {datos.especialidad}\n"
                f"Motivo de la referencia: {datos.motivo}\n"
                f"Estado actual del paciente: {datos.estado_paciente}\n\n"
                f"La fundacion asignara el medico y el horario de la cita. Recibira otro "
                f"correo con el nombre del medico en cuanto quede asignado.\n\n"
            )
        return asunto, saludo + cuerpo + firma

    # ---------------- Envio por SMTP ----------------
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

    # ---------------- Caso de uso principal ----------------
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
            raise ReglaNegocioError(f"No existe la notificacion {notificacion_id}", 404)
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
