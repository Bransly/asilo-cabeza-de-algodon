"""
CAPA DE SEGURIDAD  (aplicacion base)

Implementa los controles definidos en el punto 6 del Documento de Diseño
Arquitectonico:

  - Autenticacion: contrasena almacenada con hash seguro (scrypt con sal
    aleatoria), bloqueo temporal tras varios intentos fallidos y sesion con
    vencimiento por inactividad.
  - Autorizacion: permisos por rol y por accion. El servidor SIEMPRE vuelve a
    validar; ocultar un boton en la pantalla no es un control de seguridad.
  - Auditoria: se registra usuario, fecha, accion, entidad afectada y resultado.

La contrasena en claro nunca se guarda ni se escribe en la bitacora.
"""
from datetime import datetime, timedelta
from functools import wraps

from flask import flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import RegistroBitacora, RolUsuario, Usuario
from repository import BitacoraRepository, UsuarioRepository

# --- Parametros de seguridad -------------------------------------------------
# scrypt es una funcion de derivacion de clave "lenta" y con alto costo de
# memoria: encarece muchisimo un ataque de fuerza bruta por diccionario.
# Werkzeug genera una sal aleatoria distinta para cada usuario, de modo que dos
# personas con la misma contrasena producen hashes diferentes.
ALGORITMO_HASH = "scrypt"
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15
MINUTOS_INACTIVIDAD = 30


class ErrorAutenticacion(Exception):
    """Credenciales invalidas, usuario inactivo o cuenta bloqueada."""


# --- Hash de contrasenas -----------------------------------------------------
def cifrar_contrasena(contrasena: str) -> str:
    """Devuelve el hash con sal. Nunca se almacena la contrasena en claro."""
    return generate_password_hash(contrasena, method=ALGORITMO_HASH)


def contrasena_valida(usuario: Usuario, contrasena: str) -> bool:
    """
    Compara el hash almacenado contra la contrasena recibida. La comparacion la
    hace Werkzeug en tiempo constante para no filtrar informacion por el tiempo
    de respuesta.
    """
    return check_password_hash(usuario.hash_contrasena, contrasena)


# --- Servicio de autenticacion ----------------------------------------------
class AutenticacionService:
    def __init__(self, sesion):
        self.sesion = sesion
        self.usuarios = UsuarioRepository(sesion)
        self.bitacora = BitacoraRepository(sesion)

    def iniciar_sesion(self, nombre_usuario: str, contrasena: str) -> Usuario:
        usuario = self.usuarios.obtener_por_nombre((nombre_usuario or "").strip())

        # Mensaje unico a proposito: no se revela si el usuario existe o no.
        generico = "Usuario o contrasena incorrectos."

        if usuario is None:
            self.registrar("INICIO_SESION", "Usuario", None, "FALLIDO",
                           f"Usuario inexistente: {nombre_usuario}")
            raise ErrorAutenticacion(generico)

        if not usuario.activo:
            self.registrar("INICIO_SESION", "Usuario", usuario.id, "FALLIDO",
                           "Cuenta inactiva", usuario_id=usuario.id)
            raise ErrorAutenticacion("La cuenta esta inactiva. Consulte al administrador.")

        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.now():
            restantes = int((usuario.bloqueado_hasta - datetime.now()).total_seconds() // 60) + 1
            self.registrar("INICIO_SESION", "Usuario", usuario.id, "FALLIDO",
                           "Cuenta bloqueada", usuario_id=usuario.id)
            raise ErrorAutenticacion(
                f"Cuenta bloqueada por intentos fallidos. Intente en {restantes} minutos.")

        if not contrasena_valida(usuario, contrasena):
            usuario.intentos_fallidos += 1
            detalle = f"Intento {usuario.intentos_fallidos} de {INTENTOS_MAXIMOS}"
            if usuario.intentos_fallidos >= INTENTOS_MAXIMOS:
                usuario.bloqueado_hasta = datetime.now() + timedelta(minutes=MINUTOS_BLOQUEO)
                usuario.intentos_fallidos = 0
                detalle = f"Cuenta bloqueada {MINUTOS_BLOQUEO} minutos"
            self.usuarios.confirmar()
            self.registrar("INICIO_SESION", "Usuario", usuario.id, "FALLIDO",
                           detalle, usuario_id=usuario.id)
            raise ErrorAutenticacion(generico)

        # Ingreso correcto: se reinician los contadores.
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_acceso = datetime.now()
        self.usuarios.confirmar()

        session.clear()
        session["usuario_id"] = usuario.id
        session["usuario_nombre"] = usuario.nombre
        session["rol"] = usuario.rol.value
        session["ultima_actividad"] = datetime.now().isoformat()
        session.permanent = True

        self.registrar("INICIO_SESION", "Usuario", usuario.id, "EXITO",
                       usuario_id=usuario.id)
        return usuario

    def cerrar_sesion(self) -> None:
        self.registrar("CIERRE_SESION", "Usuario", session.get("usuario_id"), "EXITO")
        session.clear()

    def registrar(self, accion, entidad=None, entidad_id=None, resultado="EXITO",
                  detalle="", usuario_id=None):
        """Deja constancia en la bitacora de auditoria."""
        registro = RegistroBitacora(
            usuario_id=usuario_id or session.get("usuario_id"),
            usuario_nombre=session.get("usuario_nombre", "anonimo"),
            rol=session.get("rol", "-"),
            accion=accion,
            entidad=entidad or "",
            entidad_id=entidad_id,
            resultado=resultado,
            detalle=detalle[:300],
            direccion_ip=request.remote_addr or "",
        )
        self.bitacora.guardar(registro)


# --- Control de acceso en cada peticion --------------------------------------
def usuario_actual() -> dict | None:
    if "usuario_id" not in session:
        return None
    return {
        "id": session["usuario_id"],
        "nombre": session["usuario_nombre"],
        "rol": session["rol"],
    }


def sesion_expirada() -> bool:
    marca = session.get("ultima_actividad")
    if not marca:
        return True
    limite = datetime.fromisoformat(marca) + timedelta(minutes=MINUTOS_INACTIVIDAD)
    return datetime.now() > limite


def refrescar_actividad() -> None:
    session["ultima_actividad"] = datetime.now().isoformat()


def requiere_rol(*roles_permitidos):
    """
    Decorador de autorizacion. Se aplica en el servidor, en CADA peticion.
    Sin argumentos exige unicamente tener sesion abierta.
    """
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if usuario_actual() is None:
                flash("Inicie sesion para continuar.", "warning")
                return redirect(url_for("login", siguiente=request.path))

            if sesion_expirada():
                session.clear()
                flash("Su sesion vencio por inactividad. Vuelva a ingresar.", "warning")
                return redirect(url_for("login"))

            refrescar_actividad()

            if roles_permitidos:
                rol = session.get("rol")
                permitidos = [r.value if isinstance(r, RolUsuario) else r
                              for r in roles_permitidos]
                if rol not in permitidos and rol != RolUsuario.ADMINISTRADOR.value:
                    AutenticacionService(request.sesion).registrar(
                        "ACCESO_DENEGADO", vista.__name__, None, "DENEGADO",
                        f"Rol {rol} intento {request.method} {request.path}")
                    flash("Su rol no tiene permiso para realizar esa accion.", "danger")
                    return redirect(url_for("panel"))

            return vista(*args, **kwargs)
        return envoltura
    return decorador
