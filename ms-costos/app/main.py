"""
CAPA DE PRESENTACION DEL MICROSERVICIO (API REST)
Solo recibe peticiones HTTP, valida el formato y delega en la capa de negocio.
No contiene reglas ni consultas SQL.

Microservicio 1: COSTOS Y CARGOS
Documentacion interactiva: http://localhost:8001/docs
"""
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db, init_db
from .models import EstadoCargo
from .schemas import (
    CargoCrear,
    CargoRespuesta,
    EstadoCuenta,
    TarifaActualizar,
    TarifaCrear,
    TarifaRespuesta,
)
from .services import CargoService, ReglaNegocioError, TarifaService

app = FastAPI(
    title="Microservicio de Costos y Cargos",
    description=(
        "Calcula y administra los cargos de consultas, examenes de laboratorio y "
        "farmacia aplicando el descuento de la fundacion. "
        "Sistema de Administracion del Asilo de Ancianos Cabeza de Algodon."
    ),
    version="1.0.0",
)

# Permite que la aplicacion base consuma el microservicio desde el navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def al_iniciar() -> None:
    init_db()
    db = SessionLocal()
    try:
        TarifaService(db).sembrar_catalogo_inicial()
    finally:
        db.close()


def _manejar(error: ReglaNegocioError) -> HTTPException:
    return HTTPException(status_code=error.codigo, detail=error.mensaje)


# --------------------------------------------------------------------------
# Salud del servicio (lo usa Docker y la aplicacion base)
# --------------------------------------------------------------------------
@app.get("/salud", tags=["Salud"])
def salud():
    return {"servicio": "ms-costos", "estado": "activo"}


# --------------------------------------------------------------------------
# CRUD de tarifas
# --------------------------------------------------------------------------
@app.get("/tarifas", response_model=List[TarifaRespuesta], tags=["Tarifas"])
def listar_tarifas(solo_activas: bool = False, db: Session = Depends(get_db)):
    return TarifaService(db).listar(solo_activas)


@app.get("/tarifas/{tarifa_id}", response_model=TarifaRespuesta, tags=["Tarifas"])
def obtener_tarifa(tarifa_id: int, db: Session = Depends(get_db)):
    try:
        return TarifaService(db).obtener(tarifa_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.post(
    "/tarifas",
    response_model=TarifaRespuesta,
    status_code=status.HTTP_201_CREATED,
    tags=["Tarifas"],
)
def crear_tarifa(datos: TarifaCrear, db: Session = Depends(get_db)):
    return TarifaService(db).crear(datos)


@app.put("/tarifas/{tarifa_id}", response_model=TarifaRespuesta, tags=["Tarifas"])
def actualizar_tarifa(tarifa_id: int, datos: TarifaActualizar, db: Session = Depends(get_db)):
    try:
        return TarifaService(db).actualizar(tarifa_id, datos)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.delete("/tarifas/{tarifa_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tarifas"])
def eliminar_tarifa(tarifa_id: int, db: Session = Depends(get_db)):
    try:
        TarifaService(db).eliminar(tarifa_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


# --------------------------------------------------------------------------
# CRUD de cargos
# --------------------------------------------------------------------------
@app.get("/cargos", response_model=List[CargoRespuesta], tags=["Cargos"])
def listar_cargos(
    paciente_id: Optional[int] = Query(default=None),
    estado: Optional[EstadoCargo] = Query(default=None),
    db: Session = Depends(get_db),
):
    return CargoService(db).listar(paciente_id, estado)


@app.get("/cargos/{cargo_id}", response_model=CargoRespuesta, tags=["Cargos"])
def obtener_cargo(cargo_id: int, db: Session = Depends(get_db)):
    try:
        return CargoService(db).obtener(cargo_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.post(
    "/cargos",
    response_model=CargoRespuesta,
    status_code=status.HTTP_201_CREATED,
    tags=["Cargos"],
)
def registrar_cargo(datos: CargoCrear, db: Session = Depends(get_db)):
    """Registra el cargo y calcula el total con el descuento de la fundacion."""
    try:
        return CargoService(db).registrar(datos)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.put("/cargos/{cargo_id}/pagar", response_model=CargoRespuesta, tags=["Cargos"])
def pagar_cargo(cargo_id: int, db: Session = Depends(get_db)):
    try:
        return CargoService(db).marcar_pagado(cargo_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


@app.delete("/cargos/{cargo_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Cargos"])
def eliminar_cargo(cargo_id: int, db: Session = Depends(get_db)):
    try:
        CargoService(db).eliminar(cargo_id)
    except ReglaNegocioError as error:
        raise _manejar(error)


# --------------------------------------------------------------------------
# Reporte
# --------------------------------------------------------------------------
@app.get("/reportes/estado-cuenta/{paciente_id}", response_model=EstadoCuenta, tags=["Reportes"])
def estado_cuenta(paciente_id: int, db: Session = Depends(get_db)):
    """Reporte de cobros por paciente con el ahorro obtenido por la fundacion."""
    try:
        return CargoService(db).estado_cuenta(paciente_id)
    except ReglaNegocioError as error:
        raise _manejar(error)
