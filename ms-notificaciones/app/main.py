"""
CAPA DE PRESENTACION DEL MICROSERVICIO (API REST)

Microservicio 2: NOTIFICACIONES AL FAMILIAR
Documentacion interactiva: http://localhost:8002/docs
"""
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import EstadoEnvio
from .schemas import NotificacionRespuesta, SolicitudMedicaNotificar
from .services import NotificacionService, ReglaNegocioError

app = FastAPI(
    title="Microservicio de Notificaciones",
    description=(
        "Envia y registra el correo que se manda al familiar cuando se crea una "
        "solicitud de atencion medica. "
        "Sistema de Administracion del Asilo de Ancianos Cabeza de Algodon."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def al_iniciar() -> None:
    init_db()


def _manejar(error: ReglaNegocioError) -> HTTPException:
    return HTTPException(status_code=error.codigo, detail=error.mensaje)


@app.get("/salud", tags=["Salud"])
def salud():
    return {"servicio": "ms-notificaciones", "estado": "activo"}


@app.post(
    "/notificaciones/solicitud-medica",
    response_model=NotificacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    tags=["Notificaciones"],
)
def notificar_solicitud(datos: SolicitudMedicaNotificar, db: Session = Depends(get_db)):
    """Redacta el correo, lo envia al familiar y lo guarda en la bitacora."""
    return NotificacionService(db).notificar_solicitud(datos)


@app.get("/notificaciones", response_model=List[NotificacionRespuesta], tags=["Notificaciones"])
def listar_notificaciones(
    paciente_id: Optional[int] = Query(default=None),
    estado: Optional[EstadoEnvio] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Bitacora de correos enviados (evidencia para auditoria)."""
    return NotificacionService(db).listar(paciente_id, estado)


@app.get(
    "/notificaciones/{notificacion_id}",
    response_model=NotificacionRespuesta,
    tags=["Notificaciones"],
)
def obtener_notificacion(notificacion_id: int, db: Session = Depends(get_db)):
    try:
        return NotificacionService(db).obtener(notificacion_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.post(
    "/notificaciones/{notificacion_id}/reenviar",
    response_model=NotificacionRespuesta,
    status_code=status.HTTP_201_CREATED,
    tags=["Notificaciones"],
)
def reenviar_notificacion(notificacion_id: int, db: Session = Depends(get_db)):
    try:
        return NotificacionService(db).reenviar(notificacion_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.delete(
    "/notificaciones/{notificacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Notificaciones"],
)
def eliminar_notificacion(notificacion_id: int, db: Session = Depends(get_db)):
    try:
        NotificacionService(db).eliminar(notificacion_id)
    except ReglaNegocioError as error:
        raise _manejar(error)
