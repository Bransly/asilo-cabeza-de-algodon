"""
CAPA DE INTEGRACION DE LA APLICACION BASE
Aqui se concentra TODA la comunicacion con los microservicios. El resto de la
aplicacion no sabe que existe HTTP: solo llama metodos de Python.

Patron "fachada de servicio remoto": la capa de negocio pide un cargo o un
correo sin saber que detras hay una llamada HTTP.

Autenticacion entre servicios: cada peticion lleva la cabecera X-API-Key con
una clave compartida que se lee de la variable de entorno API_KEY_SERVICIOS.
Los microservicios rechazan con 401 cualquier peticion sin esa clave, de modo
que aunque su puerto quedara expuesto por error, nadie podria crear o pagar
cargos sin pasar por la aplicacion base.
"""
import os
from typing import Any, Dict, List, Optional

import requests

URL_COSTOS = os.getenv("URL_MS_COSTOS", "http://localhost:8001")
URL_NOTIFICACIONES = os.getenv("URL_MS_NOTIFICACIONES", "http://localhost:8002")
TIEMPO_ESPERA = 10  # segundos
API_KEY = os.getenv("API_KEY_SERVICIOS", "")


class MicroservicioError(Exception):
    """Falla de comunicacion o error devuelto por un microservicio."""


class _SesionServicio(requests.Session):
    """
    Sesion HTTP con la clave de servicio en cada peticion. Si el microservicio
    esta caido (conexion rechazada, tiempo agotado) la falla se convierte en
    MicroservicioError, que la capa de negocio sabe manejar: el registro clinico
    se guarda igual y el usuario recibe una advertencia (RNF-11).
    """

    def request(self, *args, **kwargs):
        try:
            return super().request(*args, **kwargs)
        except requests.RequestException as error:
            raise MicroservicioError(f"El servicio no responde ({type(error).__name__}).")


def _http() -> requests.Session:
    sesion = _SesionServicio()
    sesion.headers["X-API-Key"] = API_KEY
    return sesion


def _procesar(respuesta: requests.Response) -> Any:
    """Traduce la respuesta HTTP: un error del servicio se vuelve MicroservicioError."""
    if respuesta.status_code >= 400:
        try:
            detalle = respuesta.json().get("detail", respuesta.text)
        except ValueError:
            detalle = respuesta.text
        raise MicroservicioError(f"{respuesta.status_code}: {detalle}")
    if respuesta.status_code == 204:
        return None
    return respuesta.json()


class ClienteCostos:
    """Consume el microservicio de costos y cargos."""

    def __init__(self, url_base: str = URL_COSTOS):
        self.url = url_base.rstrip("/")
        self.http = _http()

    def disponible(self) -> bool:
        try:
            return self.http.get(f"{self.url}/salud", timeout=3).status_code == 200
        except MicroservicioError:
            return False

    def listar_tarifas(self, solo_activas: bool = True) -> List[Dict]:
        respuesta = self.http.get(
            f"{self.url}/tarifas",
            params={"solo_activas": str(solo_activas).lower()},
            timeout=TIEMPO_ESPERA,
        )
        return _procesar(respuesta)

    def registrar_cargo(self, datos: Dict) -> Dict:
        respuesta = self.http.post(f"{self.url}/cargos", json=datos, timeout=TIEMPO_ESPERA)
        return _procesar(respuesta)

    def listar_cargos(self, paciente_id: Optional[int] = None) -> List[Dict]:
        parametros = {"paciente_id": paciente_id} if paciente_id else {}
        respuesta = self.http.get(f"{self.url}/cargos", params=parametros, timeout=TIEMPO_ESPERA)
        return _procesar(respuesta)

    def pagar_cargo(self, cargo_id: int) -> Dict:
        respuesta = self.http.put(f"{self.url}/cargos/{cargo_id}/pagar", timeout=TIEMPO_ESPERA)
        return _procesar(respuesta)

    def revertir_pago(self, cargo_id: int, motivo: str) -> Dict:
        respuesta = self.http.put(f"{self.url}/cargos/{cargo_id}/revertir-pago",
                                  json={"motivo": motivo}, timeout=TIEMPO_ESPERA)
        return _procesar(respuesta)

    def eliminar_cargo(self, cargo_id: int) -> None:
        respuesta = self.http.delete(f"{self.url}/cargos/{cargo_id}", timeout=TIEMPO_ESPERA)
        _procesar(respuesta)

    def estado_cuenta(self, paciente_id: int) -> Optional[Dict]:
        respuesta = self.http.get(
            f"{self.url}/reportes/estado-cuenta/{paciente_id}", timeout=TIEMPO_ESPERA
        )
        if respuesta.status_code == 404:
            return None
        return _procesar(respuesta)


class ClienteNotificaciones:
    """Consume el microservicio de notificaciones."""

    def __init__(self, url_base: str = URL_NOTIFICACIONES):
        self.url = url_base.rstrip("/")
        self.http = _http()

    def disponible(self) -> bool:
        try:
            return self.http.get(f"{self.url}/salud", timeout=3).status_code == 200
        except MicroservicioError:
            return False

    def notificar_solicitud(self, datos: Dict) -> Dict:
        respuesta = self.http.post(
            f"{self.url}/notificaciones/solicitud-medica", json=datos, timeout=TIEMPO_ESPERA
        )
        return _procesar(respuesta)

    def listar(self, paciente_id: Optional[int] = None) -> List[Dict]:
        parametros = {"paciente_id": paciente_id} if paciente_id else {}
        respuesta = self.http.get(
            f"{self.url}/notificaciones", params=parametros, timeout=TIEMPO_ESPERA
        )
        return _procesar(respuesta)

    def reenviar(self, notificacion_id: int) -> Dict:
        respuesta = self.http.post(
            f"{self.url}/notificaciones/{notificacion_id}/reenviar", timeout=TIEMPO_ESPERA
        )
        return _procesar(respuesta)
