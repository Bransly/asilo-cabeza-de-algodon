"""Solo la aplicacion base conoce la clave X-API-Key; /salud y /docs quedan libres."""
import os
import secrets

from fastapi import HTTPException, Request, status

API_KEY = os.getenv("API_KEY_SERVICIOS", "")
RUTAS_LIBRES = {"/salud"}

if len(API_KEY) < 32:
    raise RuntimeError(
        "Defina API_KEY_SERVICIOS (mínimo 32 caracteres) en el archivo .env.")


def exigir_clave_de_servicio(request: Request) -> None:
    if request.url.path in RUTAS_LIBRES:
        return
    recibida = request.headers.get("X-API-Key", "")
    if not secrets.compare_digest(recibida, API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Clave de servicio inválida o ausente")
