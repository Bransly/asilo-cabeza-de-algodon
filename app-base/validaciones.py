import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

EDAD_MINIMA = 60          # RV-07: adulto mayor segun la Ley de Proteccion para las
EDAD_MAXIMA = 120         #        Personas de la Tercera Edad (Decreto 80-96)
MONTO_MAXIMO = Decimal("999999.99")    # RV-01: limite de la columna DECIMAL(10,2)
CUOTA_MAXIMA = Decimal("50000.00")     # RV-05
CANTIDAD_MAXIMA = 500                  # RV-11: unidades por receta
FECHA_MINIMA = date(1950, 1, 1)        # RV-08: ninguna fecha del asilo es anterior
CENTAVO = Decimal("0.01")

PATRON_CORREO = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PATRON_TELEFONO = re.compile(r"^[0-9+\- ]{0,30}$")


class ErrorNegocio(Exception):
    """Regla del asilo incumplida. Se muestra al usuario como aviso."""


class ErrorValidacion(ErrorNegocio):
    """Dato que no cumple una regla de validacion. Se muestra al usuario."""


def texto(valor, campo: str, obligatorio: bool = True, maximo: int = 300,
          minimo: int = 0) -> str:
    """RV-12: texto obligatorio, sin exceder la longitud de la columna."""
    limpio = (valor or "").strip()
    if obligatorio and not limpio:
        raise ErrorValidacion(f"El campo '{campo}' es obligatorio.")
    if limpio and len(limpio) < minimo:
        raise ErrorValidacion(f"El campo '{campo}' debe tener al menos {minimo} caracteres.")
    if len(limpio) > maximo:
        raise ErrorValidacion(f"El campo '{campo}' admite como máximo {maximo} caracteres.")
    return limpio


def entero(valor, campo: str, minimo: int | None = None, maximo: int | None = None) -> int:
    """RV-13: numeros enteros; rechaza letras y decimales."""
    try:
        numero = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorValidacion(f"El campo '{campo}' debe ser un número entero.")
    if minimo is not None and numero < minimo:
        raise ErrorValidacion(f"El campo '{campo}' debe ser como mínimo {minimo}.")
    if maximo is not None and numero > maximo:
        raise ErrorValidacion(f"El campo '{campo}' debe ser como máximo {maximo}.")
    return numero


def monto(valor, campo: str = "monto", maximo: Decimal = MONTO_MAXIMO,
          permitir_cero: bool = False) -> Decimal:
    """RV-01 a RV-03. Mas de dos decimales se rechaza en vez de redondearse en silencio."""
    try:
        cantidad = Decimal(str(valor).strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        raise ErrorValidacion(f"El {campo} debe ser un número.")
    if not cantidad.is_finite():
        raise ErrorValidacion(f"El {campo} debe ser un número.")
    if cantidad < 0 or (cantidad == 0 and not permitir_cero):
        raise ErrorValidacion(f"El {campo} debe ser mayor que cero.")
    if cantidad != cantidad.quantize(CENTAVO):
        raise ErrorValidacion(f"El {campo} admite como máximo dos decimales.")
    if cantidad > maximo:
        raise ErrorValidacion(f"El {campo} no puede ser mayor que Q{maximo:,.2f}.")
    return cantidad.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def fecha(valor, campo: str = "fecha", permitir_futura: bool = False,
          por_defecto_hoy: bool = True) -> date | None:
    """RV-08 y RV-09: fecha real, desde 1950 y, salvo que se permita, no futura."""
    if not valor:
        return date.today() if por_defecto_hoy else None
    try:
        dia = datetime.strptime(str(valor).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ErrorValidacion(f"La {campo} no es una fecha válida.")
    if dia < FECHA_MINIMA:
        raise ErrorValidacion(f"La {campo} no puede ser anterior al {FECHA_MINIMA:%d/%m/%Y}.")
    if not permitir_futura and dia > date.today():
        raise ErrorValidacion(f"La {campo} no puede estar en el futuro.")
    return dia


def fecha_hora_futura(valor, campo: str = "fecha de la cita") -> datetime:
    """RV-10: la cita que asigna la fundacion debe ser una fecha y hora futura."""
    try:
        momento = datetime.strptime(str(valor).strip(), "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        raise ErrorValidacion(f"La {campo} no es válida.")
    if momento <= datetime.now():
        raise ErrorValidacion(f"La {campo} debe ser posterior al momento actual.")
    if momento.year > date.today().year + 1:
        raise ErrorValidacion(f"La {campo} no puede programarse a más de un año.")
    return momento


def correo(valor, campo: str = "correo del familiar") -> str:
    """RV-14: formato de correo valido; sin el, el aviso al familiar fallaria."""
    limpio = texto(valor, campo, maximo=150)
    if not PATRON_CORREO.match(limpio):
        raise ErrorValidacion(f"El {campo} no tiene un formato válido.")
    return limpio.lower()


def telefono(valor) -> str:
    """RV-15: solo digitos, espacios, guiones y el signo +."""
    limpio = (valor or "").strip()
    if not PATRON_TELEFONO.match(limpio):
        raise ErrorValidacion("El teléfono solo admite números, espacios y guiones.")
    return limpio


def opcion(valor, enumeracion, campo: str):
    """RV-16: valores de listas (origen, categoria, rol) solo del catalogo."""
    try:
        return enumeracion(valor)
    except ValueError:
        raise ErrorValidacion(f"El valor indicado para '{campo}' no es válido.")


def contrasena_segura(valor: str) -> str:
    """RV-17: minimo 10 caracteres, con letras y numeros."""
    if len(valor or "") < 10:
        raise ErrorValidacion("La contraseña debe tener al menos 10 caracteres.")
    if not re.search(r"[A-Za-z]", valor) or not re.search(r"[0-9]", valor):
        raise ErrorValidacion("La contraseña debe combinar letras y números.")
    if len(valor) > 128:
        raise ErrorValidacion("La contraseña admite como máximo 128 caracteres.")
    return valor
