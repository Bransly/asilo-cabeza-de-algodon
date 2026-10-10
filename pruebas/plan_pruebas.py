"""
PLAN DE PRUEBAS AUTOMATIZADO - Sistema del Asilo Cabeza de Algodon

Ejecuta los casos CP-01 a CP-78 contra el sistema en ejecucion, por HTTP, tal
como lo haria un usuario o un atacante que se salta la pantalla. Cada caso
indica el requerimiento o regla que verifica (RF, RNF, RN o RV de la ERS v1.1).

Al terminar deja la evidencia en pruebas/resultados/:
  - registro_AAAA-MM-DD_HHMM.md   tabla legible para el informe de SQA
  - registro_AAAA-MM-DD_HHMM.csv  mismos datos para hoja de calculo

Requisitos:
  - El sistema levantado sobre una base de datos NUEVA (docker compose down -v
    y luego up), porque las pruebas cuentan con los datos de ejemplo iniciales.
  - Las mismas variables del archivo .env: CLAVE_INICIAL_ADMIN,
    CLAVE_INICIAL_USUARIOS y API_KEY_SERVICIOS.

Uso:
  python pruebas/plan_pruebas.py
  python pruebas/plan_pruebas.py --tolerancia \\
      --parar-costos "docker compose stop ms-costos" \\
      --iniciar-costos "docker compose start ms-costos" \\
      --parar-notificaciones "docker compose stop ms-notificaciones" \\
      --iniciar-notificaciones "docker compose start ms-notificaciones"
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE = os.getenv("BASE", "http://localhost:8000")
URL_COSTOS = os.getenv("URL_MS_COSTOS", "http://localhost:8001")
URL_NOTIF = os.getenv("URL_MS_NOTIFICACIONES", "http://localhost:8002")
API_KEY = os.getenv("API_KEY_SERVICIOS", "")
CLAVE_ADMIN = os.getenv("CLAVE_INICIAL_ADMIN", "")
CLAVE_USUARIOS = os.getenv("CLAVE_INICIAL_USUARIOS", "")

RESULTADOS = []
SESIONES = {}
CLAVES_NUEVAS = {}


# ------------------------------------------------------------------ apoyo
def caso(cp, area, descripcion, verifica, esperado, condicion, detalle=""):
    estado = "CORRECTO" if condicion else "FALLIDO"
    RESULTADOS.append({
        "id": cp, "area": area, "caso": descripcion, "verifica": verifica,
        "esperado": esperado, "resultado": estado, "detalle": detalle,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    marca = "  ok   " if condicion else "  FALLO"
    print(f"{marca} {cp} {descripcion}" + ("" if condicion else f"  -> {detalle}"))


def clave_inicial(usuario):
    return CLAVE_ADMIN if usuario == "admin" else CLAVE_USUARIOS


def entrar_crudo(usuario, contrasena):
    s = requests.Session()
    r = s.post(f"{BASE}/login", data={"usuario": usuario, "contrasena": contrasena})
    return s, r


def sesion(usuario):
    """Sesion lista para usar. Si es el primer ingreso, cambia la clave inicial."""
    if usuario in SESIONES:
        return SESIONES[usuario]
    clave = CLAVES_NUEVAS.get(usuario, clave_inicial(usuario))
    s, r = entrar_crudo(usuario, clave)
    if "/cuenta/contrasena" in r.url:
        nueva = f"Prueba{usuario}2026x"
        s.post(f"{BASE}/cuenta/contrasena",
               data={"actual": clave, "nueva": nueva, "confirmacion": nueva})
        CLAVES_NUEVAS[usuario] = nueva
    SESIONES[usuario] = s
    return s


def api(metodo, url, clave=True, **kw):
    cabeceras = {"X-API-Key": API_KEY} if clave else {}
    return requests.request(metodo, url, headers=cabeceras, timeout=10, **kw)


def cargos_de(paciente_id):
    return api("GET", f"{URL_COSTOS}/cargos", params={"paciente_id": paciente_id}).json()


def correos_de(paciente_id):
    return api("GET", f"{URL_NOTIF}/notificaciones", params={"paciente_id": paciente_id}).json()


def hay(texto, r):
    return texto in r.text


def numero_en(patron, texto):
    m = re.search(patron, texto)
    return int(m.group(1)) if m else None


def interno_valido(**cambios):
    datos = {
        "nombre": "Prueba Interno SQA", "edad": "81",
        "fecha_ingreso": date.today().isoformat(),
        "motivo_ingreso": "Ingreso de prueba del plan SQA.",
        "familiar_nombre": "Familiar de Prueba", "correo_familiar": "familiar.prueba@ejemplo.com",
        "telefono_familiar": "5555-1234", "cuota_mensual": "800.00",
        "psicopatologia": "Ninguna.", "padecimientos": "Hipertension arterial.",
    }
    datos.update(cambios)
    return datos


# ============================================================ 1. Seguridad
def pruebas_seguridad():
    A = "Seguridad"
    r = requests.get(f"{BASE}/pacientes", allow_redirects=False)
    caso("CP-01", A, "Sin sesion, una pantalla redirige al ingreso", "RF-36, RNF-06",
         "302 hacia /login", r.status_code == 302 and "/login" in r.headers.get("Location", ""))

    r = requests.post(f"{BASE}/cargos/1/pagar", data={"paciente_id": 1}, allow_redirects=False)
    caso("CP-02", A, "Sin sesion no se ejecuta una accion POST", "RNF-06",
         "302 hacia /login", r.status_code == 302 and "/login" in r.headers.get("Location", ""))

    _, r1 = entrar_crudo("caja", "contrasenaEquivocada1")
    _, r2 = entrar_crudo("usuarioQueNoExiste", "loQueSea123")
    generico = "Usuario o contrasena incorrectos"
    caso("CP-03", A, "Contrasena incorrecta y usuario inexistente dan el mismo mensaje",
         "RNF-08", "Mensaje generico identico", hay(generico, r1) and hay(generico, r2))

    s, r = entrar_crudo("admin", CLAVE_ADMIN)
    otra = s.get(f"{BASE}/pacientes")
    caso("CP-04", A, "Con la clave inicial solo se puede cambiar la contrasena", "RF-42, RNF-17",
         "Redirige a /cuenta/contrasena", "/cuenta/contrasena" in r.url
         and "/cuenta/contrasena" in otra.url)

    r = s.post(f"{BASE}/cuenta/contrasena",
               data={"actual": CLAVE_ADMIN, "nueva": "corta1", "confirmacion": "corta1"})
    caso("CP-05", A, "Contrasena nueva de menos de 10 caracteres se rechaza", "RV-17",
         "Rechazada con mensaje", hay("al menos 10 caracteres", r))

    r = s.post(f"{BASE}/cuenta/contrasena",
               data={"actual": CLAVE_ADMIN, "nueva": "soloLetrasLargas",
                     "confirmacion": "soloLetrasLargas"})
    caso("CP-06", A, "Contrasena sin numeros se rechaza", "RV-17", "Rechazada con mensaje",
         hay("letras y numeros", r))

    nueva = "PruebaAdmin2026x"
    r = s.post(f"{BASE}/cuenta/contrasena",
               data={"actual": CLAVE_ADMIN, "nueva": nueva, "confirmacion": nueva})
    CLAVES_NUEVAS["admin"] = nueva
    SESIONES["admin"] = s
    caso("CP-07", A, "Cambio de contrasena valido habilita el sistema", "RF-42, RNF-17",
         "Contrasena actualizada y acceso al panel", hay("Contrasena actualizada", r))

    caja = sesion("caja")
    r = caja.post(f"{BASE}/visitas/1/diagnostico", data={"diagnostico": "no autorizado"})
    caso("CP-08", A, "Caja no puede registrar un diagnostico (peticion directa)", "RN-10, RNF-06",
         "Acceso denegado", hay("no tiene permiso", r))

    r = caja.get(f"{BASE}/laboratorio")
    caso("CP-09", A, "Caja no puede abrir el modulo de laboratorio", "RF-37",
         "Acceso denegado", hay("no tiene permiso", r))

    r = caja.get(f"{BASE}/bitacora")
    caso("CP-10", A, "Caja no puede consultar la bitacora", "RF-37, RF-40", "Acceso denegado",
         hay("no tiene permiso", r))

    lab = sesion("laboratorio")
    r = lab.get(f"{BASE}/reportes/pagos-fundacion")
    caso("CP-11", A, "Laboratorio no accede a reportes financieros", "RN-10",
         "Acceso denegado", hay("no tiene permiso", r))

    medico = sesion("mgeneral")
    r = medico.get(f"{BASE}/pacientes/1")
    caso("CP-12", A, "El medico general no ve acciones de cobro", "RNF-02",
         "Sin botones de pago", 'data-tipo="pagar"' not in r.text and r.status_code == 200)

    for _ in range(5):
        entrar_crudo("enfermeria", "malaContrasena99")
    _, r = entrar_crudo("enfermeria", clave_inicial("enfermeria"))
    caso("CP-13", A, "Tras 5 intentos fallidos la cuenta se bloquea sin revelar que existe",
         "RF-39, RNF-08", "Clave correcta rechazada con el mensaje generico",
         hay(generico, r) and "/login" in r.url)

    admin = sesion("admin")
    r = admin.get(f"{BASE}/bitacora")
    caso("CP-14", A, "La bitacora registra ingresos, fallos y accesos denegados", "RF-38, RF-40",
         "INICIO_SESION, FALLIDO y ACCESO_DENEGADO presentes",
         all(t in r.text for t in ("INICIO_SESION", "ACCESO_DENEGADO", "Cuenta bloqueada")))
    caso("CP-15", A, "Ninguna contrasena queda escrita en la bitacora", "RNF-05",
         "Ni la clave inicial ni las erroneas aparecen",
         all(t not in r.text for t in (CLAVE_USUARIOS, "malaContrasena", "contrasenaEquivocada",
                                       "usuarioQueNoExiste")))

    r = requests.get(f"{BASE}/login")
    cabeceras = r.headers
    caso("CP-16", A, "Encabezados de seguridad HTTP presentes", "RNF-18",
         "CSP, X-Frame-Options, nosniff y no-store",
         "Content-Security-Policy" in cabeceras and cabeceras.get("X-Frame-Options") == "DENY"
         and cabeceras.get("X-Content-Type-Options") == "nosniff"
         and "no-store" in cabeceras.get("Cache-Control", ""))

    s, r = entrar_crudo("admin", CLAVES_NUEVAS["admin"])
    cookie = next((c for c in s.cookies if c.name == "session"), None)
    caso("CP-17", A, "La cookie de sesion es HttpOnly y SameSite=Lax", "RNF-07, RNF-18",
         "Atributos presentes", cookie is not None and cookie.has_nonstandard_attr("HttpOnly")
         and cookie.get_nonstandard_attr("SameSite") == "Lax")

    copia = requests.Session()
    copia.cookies.update(s.cookies)
    s.post(f"{BASE}/logout")
    r = copia.get(f"{BASE}/pacientes", allow_redirects=False)
    caso("CP-18", A, "Al cerrar sesion, una copia de la cookie deja de servir", "RF-36, RNF-07",
         "302 hacia /login", r.status_code == 302)
    SESIONES.pop("admin", None)

    r1 = api("GET", f"{URL_COSTOS}/cargos", clave=False)
    r2 = api("POST", f"{URL_NOTIF}/notificaciones/solicitud-medica", clave=False, json={})
    r3 = requests.get(f"{URL_COSTOS}/tarifas", headers={"X-API-Key": "clave-falsa"})
    caso("CP-19", A, "Los microservicios rechazan peticiones sin clave de servicio", "RNF-19",
         "401 sin clave o con clave falsa",
         r1.status_code == 401 and r2.status_code == 401 and r3.status_code == 401)

    r = api("GET", f"{URL_COSTOS}/tarifas")
    caso("CP-20", A, "Con la clave de servicio la API responde", "RNF-19", "200",
         r.status_code == 200)


# ===================================================== 2. Expediente y datos
def pruebas_expediente():
    A = "Expediente y validacion"
    admin = sesion("admin")

    r = admin.post(f"{BASE}/pacientes", data=interno_valido())
    pid = numero_en(r"/pacientes/(\d+)", r.url)
    caso("CP-21", A, "Alta de un interno con datos validos", "RF-01",
         "Interno registrado", hay("Interno registrado", r) and pid is not None)

    r1 = admin.post(f"{BASE}/pacientes", data=interno_valido(edad="45"))
    r2 = admin.post(f"{BASE}/pacientes", data=interno_valido(edad="130"))
    r3 = admin.post(f"{BASE}/pacientes", data=interno_valido(edad="abc"))
    caso("CP-22", A, "Edad fuera de 60-120 o no numerica se rechaza", "RV-07, RV-13",
         "Rechazada con mensaje", hay("como minimo 60", r1) and hay("como maximo 120", r2)
         and hay("numero entero", r3))

    manana = (date.today() + timedelta(days=1)).isoformat()
    r1 = admin.post(f"{BASE}/pacientes", data=interno_valido(fecha_ingreso=manana))
    r2 = admin.post(f"{BASE}/pacientes", data=interno_valido(fecha_ingreso="2026-09-31"))
    r3 = admin.post(f"{BASE}/pacientes", data=interno_valido(fecha_ingreso="1900-01-01"))
    caso("CP-23", A, "Fecha de ingreso futura, inexistente (31/09) o anterior a 1950 se rechaza",
         "RV-08, RV-09", "Rechazada", hay("no puede estar en el futuro", r1)
         and hay("no es una fecha valida", r2) and hay("no puede ser anterior", r3))

    r = admin.post(f"{BASE}/pacientes", data=interno_valido(correo_familiar="no-es-correo"))
    caso("CP-24", A, "Correo del familiar con formato invalido se rechaza", "RV-14",
         "Rechazado", hay("no tiene un formato valido", r))

    r1 = admin.post(f"{BASE}/pacientes", data=interno_valido(cuota_mensual="-100"))
    r2 = admin.post(f"{BASE}/pacientes", data=interno_valido(cuota_mensual="0"))
    r3 = admin.post(f"{BASE}/pacientes", data=interno_valido(cuota_mensual="800.555"))
    caso("CP-25", A, "Cuota negativa, cero o con 3 decimales se rechaza", "RV-01, RV-02, RV-05",
         "Rechazada", hay("mayor que cero", r1) and hay("mayor que cero", r2)
         and hay("dos decimales", r3))

    r1 = admin.post(f"{BASE}/pacientes", data=interno_valido(nombre=""))
    r2 = admin.post(f"{BASE}/pacientes", data=interno_valido(nombre="A" * 500))
    caso("CP-26", A, "Nombre vacio o de mas de 120 caracteres se rechaza", "RV-12",
         "Rechazado", hay("es obligatorio", r1) and hay("como maximo 120", r2))

    inyeccion = "Robert'); DROP TABLE pacientes;-- <script>alert(1)</script>"
    r = admin.post(f"{BASE}/pacientes", data=interno_valido(nombre=inyeccion))
    listado = admin.get(f"{BASE}/pacientes")
    caso("CP-27", A, "Inyeccion SQL y script se guardan como texto inofensivo", "RNF-10",
         "Tabla intacta y script escapado", listado.status_code == 200
         and "Rosa Elvira Perez" in listado.text and "<script>alert(1)</script>" not in listado.text
         and "&lt;script&gt;" in listado.text)

    r = admin.post(f"{BASE}/pacientes/{pid}/editar", data={"edad": "200"})
    caso("CP-28", A, "La edicion tambien valida en el servidor", "RF-02, RV-07",
         "Rechazada", hay("como maximo 120", r))

    r = requests.post(f"{BASE}/pacientes", data=interno_valido(edad="-5"),
                      cookies=admin.cookies)
    caso("CP-29", A, "Peticion directa con datos invalidos, sin pasar por la pantalla",
         "RNF-06, RV-07", "Rechazada", hay("como minimo 60", r))

    medico = sesion("mgeneral")
    r1 = medico.post(f"{BASE}/pacientes/{pid}/ficha", data={
        "psicopatologia": "Ninguna.", "padecimientos": "Hipertension arterial.",
        "alergias": "Penicilina", "observaciones": "Dieta baja en sodio."})
    r2 = medico.post(f"{BASE}/pacientes/{pid}/medicamentos", data={
        "nombre": "Losartan 50mg", "dosis": "1 tableta", "frecuencia": "Cada 24 horas"})
    r3 = medico.post(f"{BASE}/pacientes/{pid}/medicamentos", data={"nombre": ""})
    caso("CP-30", A, "Ficha medica y medicamento permanente; medicamento sin nombre se rechaza",
         "RF-04, RF-05, RV-12", "Ficha actualizada, medicamento agregado, vacio rechazado",
         hay("Ficha medica actualizada", r1) and hay("Medicamento permanente agregado", r2)
         and hay("es obligatorio", r3) and hay("Penicilina", r2))

    otro = admin.post(f"{BASE}/pacientes", data=interno_valido(nombre="Interno Para Baja"))
    bid = numero_en(r"/pacientes/(\d+)", otro.url)
    r = admin.post(f"{BASE}/pacientes/{bid}/baja")
    expediente = admin.get(f"{BASE}/pacientes/{bid}")
    caso("CP-31", A, "La baja es logica: sale del listado y el expediente se conserva",
         "RF-03, RN-11", "No aparece en internos activos; expediente accesible",
         hay("dado de baja", r) and "Interno Para Baja" not in admin.get(f"{BASE}/pacientes").text
         and expediente.status_code == 200 and hay("Interno Para Baja", expediente))
    return pid


# ================================================ 3. Flujo clinico completo
def pruebas_flujo(pid):
    A = "Flujo de atencion"
    medico, fundacion = sesion("mgeneral"), sesion("fundacion")
    especialista, lab, farmacia = sesion("especialista"), sesion("laboratorio"), sesion("farmacia")

    r = medico.post(f"{BASE}/solicitudes", data={"paciente_id": pid, "especialidad_id": 1,
                                                 "enfermero_id": 1, "motivo": ""})
    caso("CP-32", A, "Solicitud sin motivo se rechaza", "RV-12", "Rechazada",
         hay("es obligatorio", r))

    r = medico.post(f"{BASE}/solicitudes", data={"paciente_id": pid, "especialidad_id": 99,
                                                 "motivo": "Control de presion"})
    caso("CP-33", A, "Solicitud a una especialidad inexistente se rechaza", "RV-16",
         "Rechazada", hay("especialidad indicada no existe", r))

    r = medico.post(f"{BASE}/solicitudes", data={
        "paciente_id": pid, "especialidad_id": 1, "enfermero_id": 1,
        "motivo": "Presion arterial elevada en la evaluacion inicial.",
        "estado_paciente": "Estable"})
    sid = numero_en(r"Solicitud #(\d+)", r.text)
    correos = correos_de(pid)
    caso("CP-34", A, "Solicitud valida y aviso al familiar (especialidad y motivo)",
         "RF-07, RF-11, RN-02", "Solicitud creada y correo SOLICITUD_REGISTRADA",
         sid is not None and any(c["tipo"] == "SOLICITUD_REGISTRADA" for c in correos))

    pasado = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    futuro = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT09:30")
    r1 = fundacion.post(f"{BASE}/solicitudes/{sid}/asignar",
                        data={"medico_id": 2, "fecha_asignada": futuro})
    r2 = fundacion.post(f"{BASE}/solicitudes/{sid}/asignar",
                        data={"medico_id": 1, "fecha_asignada": pasado})
    caso("CP-35", A, "Medico de otra especialidad o cita en el pasado se rechaza",
         "RN-04, RV-10", "Rechazada", hay("no pertenece a la especialidad", r1)
         and hay("posterior al momento actual", r2))

    r = especialista.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 2})
    caso("CP-36", A, "No se abre visita si la fundacion no asigno medico", "RF-08, RN-03",
         "Rechazada", hay("aun no asigna medico", r))

    r = fundacion.post(f"{BASE}/solicitudes/{sid}/asignar",
                       data={"medico_id": 1, "fecha_asignada": futuro})
    correos = correos_de(pid)
    aviso = next((c for c in correos if c["tipo"] == "MEDICO_ASIGNADO"), None)
    caso("CP-37", A, "Al asignar, el familiar recibe el nombre del medico y la cita",
         "RF-09, RF-11", "Correo MEDICO_ASIGNADO con el medico",
         hay("asignada a", r) and aviso is not None and "Dr. Luis Herrera" in aviso["mensaje"])

    r = fundacion.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 3})
    caso("CP-38", A, "Una tarifa de examen no puede cobrarse como consulta", "RV-16",
         "Rechazada", hay("no corresponde a este tipo", r))

    r = fundacion.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 2})
    vid = numero_en(r"/visitas/(\d+)", r.url)
    consulta = next((c for c in cargos_de(pid) if c["tipo_servicio"] == "CONSULTA"), None)
    caso("CP-39", A, "La solicitud se convierte en visita y carga la consulta con descuento",
         "RF-10, RF-21, RN-06", "Visita abierta; Q350.00 - 35% = Q227.50",
         vid is not None and consulta is not None and consulta["total"] == 227.50)

    r = fundacion.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 2})
    caso("CP-40", A, "Una solicitud no se convierte en visita dos veces", "RN-05",
         "Rechazada", hay("ya tiene una visita", r) or hay("ya fue atendida", r)
         or len([c for c in cargos_de(pid) if c["tipo_servicio"] == "CONSULTA"]) == 1)

    r = especialista.get(f"{BASE}/visitas/{vid}")
    caso("CP-41", A, "El especialista ve la ficha medica del interno en la visita", "RF-13",
         "Ficha visible", hay("Hipertension arterial", r))

    datos = {"tarifa_id": 6, "indicaciones": "1 tableta cada 24 horas"}
    r1 = especialista.post(f"{BASE}/visitas/{vid}/recetas", data={**datos, "cantidad": "0"})
    r2 = especialista.post(f"{BASE}/visitas/{vid}/recetas", data={**datos, "cantidad": "501"})
    r3 = especialista.post(f"{BASE}/visitas/{vid}/recetas",
                           data={"tarifa_id": 6, "cantidad": "30", "indicaciones": ""})
    caso("CP-42", A, "Receta con cantidad 0, mayor a 500 o sin indicaciones se rechaza",
         "RF-19, RV-11", "Rechazada", hay("como minimo 1", r1) and hay("como maximo 500", r2)
         and hay("es obligatorio", r3))

    r = especialista.post(f"{BASE}/visitas/{vid}/recetas", data={**datos, "cantidad": "30"})
    caso("CP-43", A, "Receta valida queda pendiente de entrega y sin cobro", "RF-19, RN-07",
         "Indicado y sin cargo de medicamento", hay("Medicamento indicado", r)
         and not any(c["tipo_servicio"] == "MEDICAMENTO" for c in cargos_de(pid)))

    r = especialista.post(f"{BASE}/visitas/{vid}/examenes",
                          data={"tarifa_id": 3, "indicaciones": "En ayunas"})
    examen = next((c for c in cargos_de(pid) if c["tipo_servicio"] == "EXAMEN"), None)
    caso("CP-44", A, "El examen se cobra al solicitarlo con descuento", "RF-15, RN-07",
         "Q120.00 - 50% = Q60.00", hay("Examen solicitado", r) and examen is not None
         and examen["total"] == 60.00)

    especialista.post(f"{BASE}/visitas/{vid}/diagnostico",
                      data={"diagnostico": "Hipertension no controlada.", "observaciones": ""})
    r = especialista.post(f"{BASE}/visitas/{vid}/cerrar")
    caso("CP-45", A, "No se cierra la visita con examenes sin resultado", "RN-09",
         "Rechazada", hay("sin resultado", r))

    bandeja = lab.get(f"{BASE}/laboratorio")
    eid = numero_en(r"/examenes/(\d+)/resultado", bandeja.text)
    r1 = lab.post(f"{BASE}/examenes/{eid}/resultado", data={"resultado": "   "})
    r2 = lab.post(f"{BASE}/examenes/{eid}/resultado",
                  data={"resultado": "Hemoglobina 13.2 g/dL. Sin alteraciones."})
    r3 = lab.post(f"{BASE}/examenes/{eid}/resultado", data={"resultado": "Otro resultado"})
    caso("CP-46", A, "Resultado vacio se rechaza; el valido se guarda una sola vez",
         "RF-16, RF-17", "Vacio rechazado, valido guardado, segundo rechazado",
         hay("es obligatorio", r1) and hay("Resultado cargado", r2) and hay("ya tiene resultado", r3))

    r = especialista.get(f"{BASE}/visitas/{vid}")
    caso("CP-47", A, "El medico consulta el resultado del laboratorio", "RF-18",
         "Resultado visible en la visita", hay("Hemoglobina 13.2", r))

    bandeja = farmacia.get(f"{BASE}/farmacia")
    rid = numero_en(r"/recetas/(\d+)/entregar", bandeja.text)
    r1 = farmacia.post(f"{BASE}/recetas/{rid}/entregar")
    r2 = farmacia.post(f"{BASE}/recetas/{rid}/entregar")
    medicamento = [c for c in cargos_de(pid) if c["tipo_servicio"] == "MEDICAMENTO"]
    caso("CP-48", A, "Entregar cobra el medicamento una sola vez", "RF-20, RN-07, RN-08",
         "30 x Q3.50 - 30% = Q73.50; segunda entrega rechazada",
         hay("Medicamento entregado", r1) and hay("ya fue entregado", r2)
         and len(medicamento) == 1 and medicamento[0]["total"] == 73.50)

    especialista.post(f"{BASE}/visitas/{vid}/diagnostico",
                      data={"diagnostico": "", "observaciones": ""})
    r1 = especialista.post(f"{BASE}/visitas/{vid}/cerrar")
    especialista.post(f"{BASE}/visitas/{vid}/diagnostico",
                      data={"diagnostico": "Hipertension arterial grado 1.",
                            "observaciones": "Control en 30 dias."})
    r2 = especialista.post(f"{BASE}/visitas/{vid}/cerrar")
    caso("CP-49", A, "Sin diagnostico no se cierra; con diagnostico si", "RF-12, RF-14, RN-09",
         "Primero rechazada, luego cerrada", hay("sin registrar el diagnostico", r1)
         and hay("Visita medica cerrada", r2))

    medico_r = medico.get(f"{BASE}/pacientes/{pid}")
    caso("CP-50", A, "El historial del interno muestra la visita cerrada", "RF-06",
         "Diagnostico en el historial", hay("Hipertension arterial grado 1", medico_r))
    return pid, vid


# ============================================ 4. Costos, caja y fundacion
def pruebas_costos(pid):
    A = "Costos y caja"
    caja = sesion("caja")

    cuenta = api("GET", f"{URL_COSTOS}/reportes/estado-cuenta/{pid}").json()
    caso("CP-51", A, "Estado de cuenta del familiar con descuento", "RF-22, RF-24",
         "Subtotal Q575.00, total Q361.00, ahorro Q214.00",
         cuenta["total_sin_descuento"] == 575.0 and cuenta["total_facturado"] == 361.0
         and cuenta["total_ahorrado"] == 214.0 and cuenta["saldo_pendiente"] == 361.0)

    consulta = next(c for c in cargos_de(pid) if c["tipo_servicio"] == "CONSULTA")
    r1 = caja.post(f"{BASE}/cargos/{consulta['id']}/pagar", data={"paciente_id": pid})
    r2 = caja.post(f"{BASE}/cargos/{consulta['id']}/pagar", data={"paciente_id": pid})
    caso("CP-52", A, "Un cargo se paga una sola vez (doble clic o reenvio)", "RF-23",
         "Segundo pago rechazado", hay("marcado como pagado", r1) and hay("ya estaba cancelado", r2))

    r1 = caja.post(f"{BASE}/cargos/{consulta['id']}/revertir",
                   data={"paciente_id": pid, "motivo": ""})
    r2 = caja.post(f"{BASE}/cargos/{consulta['id']}/revertir",
                   data={"paciente_id": pid, "motivo": "Se cobro al interno equivocado"})
    estado = api("GET", f"{URL_COSTOS}/cargos/{consulta['id']}").json()["estado"]
    caso("CP-53", A, "Revertir un pago exige motivo y devuelve el cargo a pendiente", "RF-41",
         "Sin motivo rechazado; con motivo PENDIENTE", hay("es obligatorio", r1)
         and hay("se revirtio", r2) and estado == "PENDIENTE")
    caja.post(f"{BASE}/cargos/{consulta['id']}/pagar", data={"paciente_id": pid})

    r = api("DELETE", f"{URL_COSTOS}/cargos/{consulta['id']}")
    caso("CP-54", A, "No se elimina un cargo ya pagado", "RN-13", "400",
         r.status_code == 400)

    base = {"tipo_servicio": "EXAMEN", "descripcion": "Tarifa de prueba SQA"}
    r1 = api("POST", f"{URL_COSTOS}/tarifas", json={**base, "precio_base": 100,
                                                     "descuento_fundacion": 150})
    r2 = api("POST", f"{URL_COSTOS}/tarifas", json={**base, "precio_base": -5})
    r3 = api("POST", f"{URL_COSTOS}/tarifas", json={**base, "precio_base": "10.005"})
    r4 = api("POST", f"{URL_COSTOS}/tarifas", json={**base, "precio_base": 100,
                                                     "descuento_fundacion": -1})
    caso("CP-55", A, "Descuento fuera de 0-100, precio negativo o con 3 decimales se rechaza",
         "RV-01, RV-03, RV-04", "422 en los cuatro casos",
         all(r.status_code == 422 for r in (r1, r2, r3, r4)))

    t = api("POST", f"{URL_COSTOS}/tarifas", json={**base, "precio_base": "0.25",
                                                    "descuento_fundacion": "50"}).json()
    c = api("POST", f"{URL_COSTOS}/cargos", json={"paciente_id": pid,
                                                  "paciente_nombre": "Prueba Interno SQA",
                                                  "tarifa_id": t["id"], "cantidad": 1}).json()
    caso("CP-56", A, "Redondeo comercial a centavos con Decimal", "RV-03",
         "Q0.25 - 50% = Q0.125 -> Q0.13", c["total"] == 0.13)

    api("PUT", f"{URL_COSTOS}/tarifas/{t['id']}", json={"precio_base": "99.00"})
    despues = api("GET", f"{URL_COSTOS}/cargos/{c['id']}").json()
    caso("CP-57", A, "Cambiar la tarifa no altera un cargo ya generado", "RN-06",
         "El cargo conserva Q0.13", despues["total"] == 0.13 and despues["precio_base"] == 0.25)
    api("DELETE", f"{URL_COSTOS}/cargos/{c['id']}")
    api("PUT", f"{URL_COSTOS}/tarifas/{t['id']}", json={"activo": False})

    hoy = date.today().isoformat()
    don = {"origen": "EMPRESA_NACIONAL", "donante": "Empresa de Prueba S.A.", "monto": "1500.00",
           "fecha": hoy, "recibo": "R-001"}
    r1 = caja.post(f"{BASE}/caja/donaciones", data=don)
    r2 = caja.post(f"{BASE}/caja/donaciones", data={**don, "origen": "MARCIANO"})
    r3 = caja.post(f"{BASE}/caja/donaciones", data={**don, "monto": "-10"})
    r4 = caja.post(f"{BASE}/caja/donaciones",
                   data={**don, "fecha": (date.today() + timedelta(days=3)).isoformat()})
    caso("CP-58", A, "Donacion valida; origen inventado, monto negativo o fecha futura se rechaza",
         "RF-26, RV-01, RV-08, RV-16", "Una registrada, tres rechazadas",
         hay("Donacion registrada", r1) and hay("no es valido", r2)
         and hay("mayor que cero", r3) and hay("futuro", r4))

    gasto = {"categoria": "ENERGIA_ELECTRICA", "descripcion": "Energia electrica del mes",
             "monto": "650.40", "fecha": hoy}
    r1 = caja.post(f"{BASE}/caja/gastos", data=gasto)
    r2 = caja.post(f"{BASE}/caja/gastos", data={**gasto, "monto": "abc"})
    caso("CP-59", A, "Gasto valido; monto con letras se rechaza", "RF-28, RV-13",
         "Uno registrado, otro rechazado", hay("Gasto registrado", r1) and hay("debe ser un numero", r2))

    anio, mes = date.today().year, date.today().month
    r1 = caja.post(f"{BASE}/caja/cuotas", data={"anio": anio, "mes": mes})
    r2 = caja.post(f"{BASE}/caja/cuotas", data={"anio": anio, "mes": mes})
    r3 = caja.post(f"{BASE}/caja/cuotas", data={"anio": anio, "mes": 13})
    caso("CP-60", A, "Las cuotas del mes se generan una sola vez; mes 13 se rechaza",
         "RF-27, RV-06", "Generadas; segunda vez sin duplicar; mes invalido rechazado",
         hay("Se generaron", r1) and hay("ya estaban generadas", r2) and hay("como maximo 12", r3))

    pantalla = caja.get(f"{BASE}/caja?anio={anio}&mes={mes}")
    cid = numero_en(r"/cuotas/(\d+)/cobrar", pantalla.text)
    r1 = caja.post(f"{BASE}/cuotas/{cid}/cobrar", data={"anio": anio, "mes": mes})
    r2 = caja.post(f"{BASE}/cuotas/{cid}/cobrar", data={"anio": anio, "mes": mes})
    caso("CP-61", A, "Una cuota se cobra una sola vez", "RF-27", "Segundo cobro rechazado",
         hay("Cuota cobrada", r1) and hay("ya fue cobrada", r2))

    total = sum(c["total"] for c in api("GET", f"{URL_COSTOS}/cargos").json())
    r1 = caja.post(f"{BASE}/caja/pagos-fundacion",
                   data={"monto": f"{total + 100:.2f}", "referencia": "FVD-0001", "fecha": hoy})
    r2 = caja.post(f"{BASE}/caja/pagos-fundacion",
                   data={"monto": "200.00", "referencia": "FVD-0001", "fecha": hoy})
    r3 = caja.post(f"{BASE}/caja/pagos-fundacion",
                   data={"monto": "50.00", "referencia": "FVD-0001", "fecha": hoy})
    caso("CP-62", A, "Pago a la fundacion: no mayor que la deuda y sin referencia repetida",
         "RF-25, RF-43, RV-01", "Excedente rechazado, pago valido, referencia duplicada rechazada",
         hay("mayor que la deuda", r1) and hay("Pago a la fundacion registrado", r2)
         and hay("Ya existe un pago", r3))
    return total


# ================================================================ 5. Reportes
def pruebas_reportes(pid, facturado):
    A = "Reportes"
    caja, medico, lab = sesion("caja"), sesion("mgeneral"), sesion("laboratorio")
    hoy = date.today().isoformat()
    casos = [
        ("CP-63", "costos-por-cita", caja, "RF-29", "Dr. Luis Herrera (Cardiologia)"),
        ("CP-64", "analisis-medico", medico, "RF-30", "Hipertension arterial grado 1"),
        ("CP-65", "cobros-por-paciente", caja, "RF-31", "Q361.00"),
        ("CP-66", "pagos-fundacion", caja, "RF-32, RF-25", "Deuda actual con la fundacion"),
        ("CP-67", "entradas", caja, "RF-33", "Pagos a la fundacion del periodo"),
        ("CP-68", "examenes-por-paciente", lab, "RF-34", "Hemoglobina 13.2"),
        ("CP-69", "medicamentos-por-paciente", medico, "RF-35", "Losartan"),
    ]
    for cp, clave, quien, rf, texto in casos:
        r = quien.get(f"{BASE}/reportes/{clave}", params={"paciente_id": pid,
                                                          "desde": hoy, "hasta": hoy})
        caso(cp, A, f"Reporte '{clave}' con datos del periodo", rf, f"Contiene '{texto}'",
             r.status_code == 200 and hay(texto, r))

    r = caja.get(f"{BASE}/reportes/pagos-fundacion")
    deuda = facturado - 200.00
    caso("CP-70", A, "La deuda con la fundacion es lo facturado menos lo pagado", "RF-25",
         f"Deuda Q{deuda:,.2f}", hay(f"Q{deuda:,.2f}", r))

    manana = (date.today() + timedelta(days=1)).isoformat()
    r = caja.get(f"{BASE}/reportes/cobros-por-paciente",
                 params={"paciente_id": pid, "desde": manana, "hasta": manana})
    caso("CP-71", A, "El filtro por rango de fechas excluye lo que esta fuera del periodo",
         "RF-31", "Sin el cargo de hoy", r.status_code == 200 and not hay("Q361.00", r))


# ====================================================== 6. Tolerancia a fallas
def ejecutar(comando):
    # Sin capturar la salida: un servicio que se reinicia en segundo plano
    # heredaria la tuberia y la prueba quedaria esperando indefinidamente.
    subprocess.run(comando, shell=True, check=False, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    time.sleep(3)


def pruebas_tolerancia(args, pid):
    A = "Tolerancia a fallas"
    medico, especialista, farmacia = sesion("mgeneral"), sesion("especialista"), sesion("farmacia")

    ejecutar(args.parar_notificaciones)
    r = medico.post(f"{BASE}/solicitudes", data={
        "paciente_id": 1, "especialidad_id": 4, "motivo": "Control geriatrico de rutina"})
    caso("CP-72", A, "Sin servicio de correo la solicitud se guarda y se advierte",
         "RNF-11, RN-12", "Solicitud creada con advertencia", hay("enviada a la fundacion", r)
         and hay("no se pudo avisar al familiar", r))
    ejecutar(args.iniciar_notificaciones)

    # Se prepara una receta pendiente y luego se detiene el servicio de costos.
    fundacion = sesion("fundacion")
    sid = numero_en(r"Solicitud #(\d+)", r.text)
    futuro = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT10:00")
    fundacion.post(f"{BASE}/solicitudes/{sid}/asignar", data={"medico_id": 4, "fecha_asignada": futuro})
    r = fundacion.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 1})
    vid = numero_en(r"/visitas/(\d+)", r.url)
    especialista.post(f"{BASE}/visitas/{vid}/recetas",
                      data={"tarifa_id": 7, "cantidad": "10", "indicaciones": "Cada 12 horas"})
    rid = numero_en(r"/recetas/(\d+)/entregar", farmacia.get(f"{BASE}/farmacia").text)

    ejecutar(args.parar_costos)
    r = farmacia.post(f"{BASE}/recetas/{rid}/entregar")
    caso("CP-73", A, "Sin servicio de costos la entrega se registra y se advierte el cargo",
         "RNF-11, RN-12", "Entregado con advertencia", hay("Medicamento entregado", r)
         and hay("no se pudo enviar al servicio de costos", r))
    r = sesion("caja").get(f"{BASE}/reportes/pagos-fundacion")
    caso("CP-74", A, "El reporte advierte que no incluye cargos si costos no responde",
         "RNF-12", "Aviso visible", hay("no respondio", r))
    ejecutar(args.iniciar_costos)


# ================================================ 7. Administracion de usuarios
def pruebas_usuarios():
    A = "Administracion de usuarios"
    admin = sesion("admin")
    lista = admin.get(f"{BASE}/usuarios").text
    ids = {u: int(i) for u, i in re.findall(
        r'<code>([a-z]+)</code>(?:(?!<code>).)*?/usuarios/(\d+)/restablecer', lista, re.S)}

    r = admin.post(f"{BASE}/usuarios/{ids['enfermeria']}/desbloquear")
    _, r2 = entrar_crudo("enfermeria", clave_inicial("enfermeria"))
    caso("CP-75", A, "El administrador desbloquea una cuenta bloqueada", "RF-44",
         "Desbloqueada; el usuario puede ingresar", hay("desbloqueada", r)
         and "/cuenta/contrasena" in r2.url)

    vieja = sesion("caja")
    r = admin.post(f"{BASE}/usuarios/{ids['caja']}/restablecer")
    temporal = (re.search(r"Clave temporal de caja: (\S+) \.", r.text) or [None, ""])[1]
    sigue = vieja.get(f"{BASE}/caja", allow_redirects=False)
    s, r2 = entrar_crudo("caja", temporal)
    bitacora = admin.get(f"{BASE}/bitacora").text
    caso("CP-76", A, "Restablecer clave: temporal de un solo uso, cierra la sesion y no queda en bitacora",
         "RF-44, RNF-05", "Clave temporal obliga a cambiarla; sesion anterior cerrada",
         bool(temporal) and sigue.status_code == 302 and "/cuenta/contrasena" in r2.url
         and temporal not in bitacora and "RESTABLECE_CONTRASENA" in bitacora)
    nueva = "Pruebacaja2026x"
    s.post(f"{BASE}/cuenta/contrasena", data={"actual": temporal, "nueva": nueva, "confirmacion": nueva})
    CLAVES_NUEVAS["caja"] = nueva
    SESIONES["caja"] = s

    r = admin.post(f"{BASE}/usuarios/{ids['farmacia']}/desactivar")
    _, r2 = entrar_crudo("farmacia", CLAVES_NUEVAS.get("farmacia", ""))
    r3 = sesion("caja").post(f"{BASE}/usuarios/{ids['farmacia']}/activar")
    r4 = admin.post(f"{BASE}/usuarios/{ids['admin']}/desactivar")
    admin.post(f"{BASE}/usuarios/{ids['farmacia']}/activar")
    caso("CP-77", A, "Una cuenta desactivada no ingresa; solo el administrador administra cuentas",
         "RF-44, RF-37", "Ingreso rechazado; caja denegado; no se desactiva a si mismo",
         hay("desactivada", r) and hay("Usuario o contrasena incorrectos", r2)
         and hay("no tiene permiso", r3) and hay("su propia cuenta", r4))


def pruebas_permisos_expediente():
    A = "Seguridad"
    lab, fun, medico, caja = sesion("laboratorio"), sesion("fundacion"), sesion("mgeneral"), sesion("caja")
    r1 = lab.get(f"{BASE}/pacientes/1")
    r2 = fun.get(f"{BASE}/pacientes")
    r3 = medico.get(f"{BASE}/pacientes/1")
    r4 = caja.get(f"{BASE}/pacientes/1")
    caso("CP-78", A, "Laboratorio y fundacion no abren expedientes; solo caja ve la cuenta del familiar",
         "RN-10, RF-37", "Laboratorio y fundacion denegados; medico sin estado de cuenta; caja con estado de cuenta",
         hay("no tiene permiso", r1) and hay("no tiene permiso", r2)
         and r3.status_code == 200 and "Estado de cuenta" not in r3.text
         and hay("Estado de cuenta", r4))


# =================================================================== registro
def guardar_registro():
    carpeta = Path(__file__).parent / "resultados"
    carpeta.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")
    columnas = ["id", "area", "caso", "verifica", "esperado", "resultado", "detalle", "fecha"]
    with open(carpeta / f"registro_{marca}.csv", "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas)
        escritor.writeheader()
        escritor.writerows(RESULTADOS)

    correctos = sum(1 for r in RESULTADOS if r["resultado"] == "CORRECTO")
    lineas = [
        "# Registro de ejecucion del plan de pruebas",
        "",
        f"- Fecha: {datetime.now():%d/%m/%Y %H:%M}",
        f"- Sistema probado: {BASE}",
        f"- Casos ejecutados: {len(RESULTADOS)}",
        f"- Correctos: {correctos}",
        f"- Fallidos: {len(RESULTADOS) - correctos}",
        "",
        "| ID | Area | Caso | Verifica | Resultado esperado | Resultado |",
        "|---|---|---|---|---|---|",
    ]
    for r in RESULTADOS:
        lineas.append(f"| {r['id']} | {r['area']} | {r['caso']} | {r['verifica']} | "
                      f"{r['esperado']} | {r['resultado']} |")
    (carpeta / f"registro_{marca}.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return carpeta / f"registro_{marca}.md", correctos


def main():
    p = argparse.ArgumentParser(description="Plan de pruebas del sistema del asilo")
    p.add_argument("--tolerancia", action="store_true",
                   help="Incluye CP-72 a CP-74 (detiene y reinicia microservicios)")
    p.add_argument("--parar-costos", default="docker compose stop ms-costos")
    p.add_argument("--iniciar-costos", default="docker compose start ms-costos")
    p.add_argument("--parar-notificaciones", default="docker compose stop ms-notificaciones")
    p.add_argument("--iniciar-notificaciones", default="docker compose start ms-notificaciones")
    args = p.parse_args()

    faltan = [n for n, v in (("CLAVE_INICIAL_ADMIN", CLAVE_ADMIN),
                             ("CLAVE_INICIAL_USUARIOS", CLAVE_USUARIOS),
                             ("API_KEY_SERVICIOS", API_KEY)) if not v]
    if faltan:
        sys.exit("Defina estas variables (las mismas del .env): " + ", ".join(faltan))

    print(f"Plan de pruebas contra {BASE}\n")
    pruebas_seguridad()
    pid = pruebas_expediente()
    pid, _ = pruebas_flujo(pid)
    facturado = pruebas_costos(pid)
    pruebas_reportes(pid, facturado)
    if args.tolerancia:
        pruebas_tolerancia(args, pid)
    pruebas_usuarios()
    pruebas_permisos_expediente()

    archivo, correctos = guardar_registro()
    print(f"\n{correctos} de {len(RESULTADOS)} casos correctos. Registro: {archivo}")
    sys.exit(0 if correctos == len(RESULTADOS) else 1)


if __name__ == "__main__":
    main()
