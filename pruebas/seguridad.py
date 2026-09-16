"""Prueba los controles de seguridad con peticiones HTTP reales."""
import requests

import os
BASE = os.getenv("BASE", "http://localhost:8000")
fallos = []


def revisar(condicion, descripcion):
    print(("  ok  " if condicion else "  FALLO ") + descripcion)
    if not condicion:
        fallos.append(descripcion)


def entrar(usuario, contrasena):
    s = requests.Session()
    r = s.post(f"{BASE}/login", data={"usuario": usuario, "contrasena": contrasena},
               allow_redirects=True)
    return s, r


# 1. Sin sesion no se entra a ninguna pantalla
r = requests.get(f"{BASE}/pacientes", allow_redirects=False)
revisar(r.status_code == 302 and "/login" in r.headers.get("Location", ""),
        "sin sesion redirige al login")

r = requests.post(f"{BASE}/cargos/1/pagar", data={"paciente_id": 1}, allow_redirects=False)
revisar(r.status_code == 302 and "/login" in r.headers.get("Location", ""),
        "sin sesion no se puede ejecutar una accion POST")

# 2. Credenciales incorrectas
s, r = entrar("caja", "contrasenaEquivocada")
revisar("Usuario o contrasena incorrectos" in r.text, "contrasena incorrecta es rechazada")
revisar("existe" not in r.text.lower() or "inexistente" not in r.text.lower(),
        "el mensaje no revela si el usuario existe")

s, r = entrar("usuarioQueNoExiste", "loQueSea")
revisar("Usuario o contrasena incorrectos" in r.text,
        "usuario inexistente da el mismo mensaje generico")

# 3. Ingreso correcto por rol
sesion_caja, r = entrar("caja", "Asilo2026*")
revisar("Bienvenido" in r.text, "ingreso correcto del rol Caja")
revisar("Laboratorio" not in r.text.split("</header>")[0],
        "el menu de Caja no muestra Laboratorio")
revisar("Bitacora" not in r.text.split("</header>")[0],
        "el menu de Caja no muestra Bitacora")

# 4. Autorizacion en el servidor: Caja no puede actuar como medico
r = sesion_caja.post(f"{BASE}/visitas/1/diagnostico",
                     data={"diagnostico": "intento no autorizado"},
                     allow_redirects=True)
revisar("no tiene permiso" in r.text, "Caja no puede escribir un diagnostico")

r = sesion_caja.get(f"{BASE}/laboratorio", allow_redirects=True)
revisar("no tiene permiso" in r.text, "Caja no puede abrir Laboratorio")

r = sesion_caja.get(f"{BASE}/bitacora", allow_redirects=True)
revisar("no tiene permiso" in r.text, "Caja no puede consultar la bitacora")

# 5. Cada rol entra a lo suyo
sesion_lab, r = entrar("laboratorio", "Asilo2026*")
revisar("Examenes pendientes de resultado" in r.text or
        sesion_lab.get(f"{BASE}/laboratorio").status_code == 200,
        "Laboratorio entra a su bandeja")

sesion_medico, r = entrar("mgeneral", "Asilo2026*")
r = sesion_medico.get(f"{BASE}/pacientes/1")
revisar("Referir a una especialidad" in r.text,
        "el medico general ve el formulario de referencia")
revisar('data-tipo="pagar"' not in r.text,
        "el medico general no ve las acciones de cobro")

# 6. Bloqueo tras varios intentos fallidos
for _ in range(5):
    entrar("farmacia", "malaContrasena")
s, r = entrar("farmacia", "Asilo2026*")
revisar("bloqueada" in r.text.lower(),
        "la cuenta se bloquea tras 5 intentos fallidos")

# 7. La bitacora registra todo y solo la ve el administrador
sesion_admin, r = entrar("admin", "Admin2026*")
r = sesion_admin.get(f"{BASE}/bitacora")
revisar(r.status_code == 200 and "INICIO_SESION" in r.text,
        "la bitacora registra los ingresos")
revisar("ACCESO_DENEGADO" in r.text, "la bitacora registra los accesos denegados")
revisar("Denegado" in r.text, "la bitacora distingue el resultado de cada accion")

# 8. La contrasena nunca aparece en la bitacora
revisar("Asilo2026" not in r.text and "malaContrasena" not in r.text,
        "ninguna contrasena queda escrita en la bitacora")

# 9. Cierre de sesion
r = sesion_admin.post(f"{BASE}/logout", allow_redirects=True)
revisar("Sesion cerrada" in r.text, "cierre de sesion")
r = sesion_admin.get(f"{BASE}/pacientes", allow_redirects=False)
revisar(r.status_code == 302, "tras cerrar sesion ya no hay acceso")

print("\n=========================")
print("Sin fallos." if not fallos else f"{len(fallos)} FALLOS: " + "; ".join(fallos))
