import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import validaciones as v
from models import RegistroBitacora, RolUsuario, Usuario
from repository import BitacoraRepository, UsuarioRepository

ALGORITMO_HASH = "scrypt"
INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 15
MINUTOS_INACTIVIDAD = 30


class ErrorAutenticacion(Exception):
    """Credenciales invalidas, usuario inactivo o cuenta bloqueada."""


# Mensaje unico para no revelar que usuarios existen; el motivo real va a la bitacora.
MENSAJE_GENERICO = ("Usuario o contraseña incorrectos, o la cuenta está bloqueada "
                    "temporalmente.")


def enmascarar(nombre: str) -> str:
    # A veces la persona escribe su contrasena en el campo de usuario por error.
    nombre = (nombre or "").strip()[:40]
    return (nombre[:2] + "***") if nombre else "(vacio)"


def cifrar_contrasena(contrasena: str) -> str:
    return generate_password_hash(contrasena, method=ALGORITMO_HASH)


def contrasena_valida(usuario: Usuario, contrasena: str) -> bool:
    return check_password_hash(usuario.hash_contrasena, contrasena)


class AutenticacionService:
    def __init__(self, sesion):
        self.sesion = sesion
        self.usuarios = UsuarioRepository(sesion)
        self.bitacora = BitacoraRepository(sesion)

    def iniciar_sesion(self, nombre_usuario: str, contrasena: str) -> Usuario:
        usuario = self.usuarios.obtener_por_nombre((nombre_usuario or "").strip())

        generico = MENSAJE_GENERICO

        if usuario is None:
            self.registrar("INICIO_SESION", "Usuario", None, "FALLIDO",
                           f"Usuario inexistente: {enmascarar(nombre_usuario)}")
            raise ErrorAutenticacion(generico)

        if not usuario.activo:
            self.registrar("INICIO_SESION", "Usuario", usuario.id, "FALLIDO",
                           "Cuenta inactiva", usuario_id=usuario.id)
            raise ErrorAutenticacion(generico)

        if usuario.bloqueado_hasta and usuario.bloqueado_hasta > datetime.now():
            self.registrar("INICIO_SESION", "Usuario", usuario.id, "FALLIDO",
                           "Cuenta bloqueada", usuario_id=usuario.id)
            raise ErrorAutenticacion(generico)

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

        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.ultimo_acceso = datetime.now()
        # Token nuevo en cada ingreso: invalida sesiones anteriores (fijacion de sesion).
        usuario.token_sesion = secrets.token_hex(32)
        self.usuarios.confirmar()

        session.clear()
        session["usuario_id"] = usuario.id
        session["usuario_nombre"] = usuario.nombre
        session["rol"] = usuario.rol.value
        session["token"] = usuario.token_sesion
        session["debe_cambiar"] = bool(usuario.debe_cambiar_contrasena)
        session["ultima_actividad"] = datetime.now().isoformat()
        session["inicio"] = datetime.now().isoformat()
        session.permanent = True

        self.registrar("INICIO_SESION", "Usuario", usuario.id, "EXITO",
                       usuario_id=usuario.id)
        return usuario

    def cerrar_sesion(self) -> None:
        self.registrar("CIERRE_SESION", "Usuario", session.get("usuario_id"), "EXITO")
        usuario = self.usuarios.obtener(session.get("usuario_id") or 0)
        if usuario is not None:
            # Sin token en el servidor, una cookie copiada ya no sirve.
            usuario.token_sesion = None
            self.usuarios.confirmar()
        session.clear()

    def cambiar_contrasena(self, actual: str, nueva: str, confirmacion: str) -> None:
        usuario = self.usuarios.obtener(session.get("usuario_id") or 0)
        if usuario is None:
            raise ErrorAutenticacion("Inicie sesión para continuar.")
        if not contrasena_valida(usuario, actual or ""):
            self.registrar("CAMBIO_CONTRASENA", "Usuario", usuario.id, "FALLIDO",
                           "Contraseña actual incorrecta")
            raise ErrorAutenticacion("La contraseña actual no es correcta.")
        if nueva != confirmacion:
            raise ErrorAutenticacion("La confirmación no coincide con la nueva contraseña.")
        if contrasena_valida(usuario, nueva):
            raise ErrorAutenticacion("La nueva contraseña debe ser distinta de la actual.")
        try:
            v.contrasena_segura(nueva)
        except v.ErrorValidacion as error:
            raise ErrorAutenticacion(str(error))
        usuario.hash_contrasena = cifrar_contrasena(nueva)
        usuario.debe_cambiar_contrasena = False
        usuario.token_sesion = secrets.token_hex(32)
        self.usuarios.confirmar()
        session["token"] = usuario.token_sesion
        session["debe_cambiar"] = False
        self.registrar("CAMBIO_CONTRASENA", "Usuario", usuario.id, "EXITO")

    def registrar(self, accion, entidad=None, entidad_id=None, resultado="EXITO",
                  detalle="", usuario_id=None):
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


class UsuarioService:
    def __init__(self, sesion):
        self.usuarios = UsuarioRepository(sesion)

    def listar(self):
        return self.usuarios.listar()

    def _obtener(self, usuario_id: int) -> Usuario:
        usuario = self.usuarios.obtener(usuario_id)
        if usuario is None:
            raise v.ErrorNegocio("El usuario indicado no existe.")
        return usuario

    def restablecer_contrasena(self, usuario_id: int) -> tuple[Usuario, str]:
        usuario = self._obtener(usuario_id)
        temporal = "Tmp-" + secrets.token_urlsafe(9)
        usuario.hash_contrasena = cifrar_contrasena(temporal)
        usuario.debe_cambiar_contrasena = True
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.token_sesion = None
        self.usuarios.confirmar()
        return usuario, temporal

    def desbloquear(self, usuario_id: int) -> Usuario:
        usuario = self._obtener(usuario_id)
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        self.usuarios.confirmar()
        return usuario

    def cambiar_estado(self, usuario_id: int, activo: bool) -> Usuario:
        usuario = self._obtener(usuario_id)
        if not activo and usuario.id == session.get("usuario_id"):
            raise v.ErrorNegocio("No puede desactivar su propia cuenta.")
        usuario.activo = activo
        if not activo:
            usuario.token_sesion = None
        self.usuarios.confirmar()
        return usuario


def usuario_actual() -> dict | None:
    if "usuario_id" not in session:
        return None
    return {
        "id": session["usuario_id"],
        "nombre": session["usuario_nombre"],
        "rol": session["rol"],
    }


HORAS_MAXIMAS_SESION = 8


def sesion_expirada() -> bool:
    marca = session.get("ultima_actividad")
    inicio = session.get("inicio")
    if not marca or not inicio:
        return True
    ahora = datetime.now()
    if ahora > datetime.fromisoformat(marca) + timedelta(minutes=MINUTOS_INACTIVIDAD):
        return True
    return ahora > datetime.fromisoformat(inicio) + timedelta(hours=HORAS_MAXIMAS_SESION)


def sesion_vigente_en_servidor() -> bool:
    usuario = UsuarioRepository(request.sesion).obtener(session.get("usuario_id") or 0)
    return (usuario is not None and usuario.activo and usuario.token_sesion is not None
            and secrets.compare_digest(usuario.token_sesion, session.get("token", "")))


def refrescar_actividad() -> None:
    session["ultima_actividad"] = datetime.now().isoformat()


def requiere_rol(*roles_permitidos):
    # Sin roles solo exige sesion abierta.
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            if usuario_actual() is None:
                flash("Inicie sesión para continuar.", "warning")
                return redirect(url_for("login", siguiente=request.path))

            if sesion_expirada() or not sesion_vigente_en_servidor():
                session.clear()
                flash("Su sesión venció o fue cerrada. Vuelva a ingresar.", "warning")
                return redirect(url_for("login"))

            refrescar_actividad()

            # Con la contrasena inicial solo se puede entrar a cambiarla.
            if session.get("debe_cambiar") and request.endpoint != "cambiar_contrasena":
                flash("Por seguridad, cambie su contraseña inicial antes de continuar.",
                      "warning")
                return redirect(url_for("cambiar_contrasena"))

            if roles_permitidos:
                rol = session.get("rol")
                permitidos = [r.value if isinstance(r, RolUsuario) else r
                              for r in roles_permitidos]
                if rol not in permitidos and rol != RolUsuario.ADMINISTRADOR.value:
                    AutenticacionService(request.sesion).registrar(
                        "ACCESO_DENEGADO", vista.__name__, None, "DENEGADO",
                        f"Rol {rol} intento {request.method} {request.path}")
                    flash("Su rol no tiene permiso para realizar esa acción.", "danger")
                    return redirect(url_for("panel"))

            return vista(*args, **kwargs)
        return envoltura
    return decorador
