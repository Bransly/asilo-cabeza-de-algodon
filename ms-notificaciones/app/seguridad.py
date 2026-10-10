"""
AUTENTICACION ENTRE SERVICIOS

Solo la aplicacion base puede llamar a este microservicio. Cada peticion debe
traer la cabecera X-API-Key con la clave compartida API_KEY_SERVICIOS, que se
define en el archivo .env (fuera del repositorio) y nunca viaja al navegador.

Sin la clave, la respuesta es 401. Asi, aunque el puerto del microservicio
quedara expuesto por error, nadie podria crear, pagar o borrar registros
saltandose los permisos por rol de la aplicacion base.

Quedan libres /salud (lo usan Docker y el indicador de estado) y la
documentacion /docs, que solo describe la API y no ejecuta nada sin la clave.
"""
import os
import secrets

from fastapi import HTTPException, Request, status

API_KEY = os.getenv("API_KEY_SERVICIOS", "")
RUTAS_LIBRES = {"/salud"}

if len(API_KEY) < 32:
    raise RuntimeError(
        "Defina API_KEY_SERVICIOS (minimo 32 caracteres) en el archivo .env.")


def exigir_clave_de_servicio(request: Request) -> None:
    if request.url.path in RUTAS_LIBRES:
        return
    recibida = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(recibida, API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Clave de servicio invalida o ausente")
