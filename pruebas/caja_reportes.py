"""Prueba el modulo de caja y los siete reportes del enunciado."""
import os
import re
from datetime import date, datetime, timedelta

import requests

BASE = os.getenv("BASE", "http://localhost:8010")
fallos = []


def revisar(condicion, descripcion):
    print(("  ok   " if condicion else "  FALLO ") + descripcion)
    if not condicion:
        fallos.append(descripcion)


def entrar(usuario, contrasena):
    s = requests.Session()
    s.post(f"{BASE}/login", data={"usuario": usuario, "contrasena": contrasena})
    return s


# ---------------------------------------------------- flujo clinico previo
s = entrar("admin", "Admin2026*")
revisar(s.get(f"{BASE}/pacientes").status_code == 200, "ingreso del administrador")

r = s.post(f"{BASE}/solicitudes", data={
    "paciente_id": 1, "especialidad_id": 1, "enfermero_id": 1,
    "motivo": "Presion arterial elevada", "estado_paciente": "Estable"})
revisar("enviada a la fundacion" in r.text, "solicitud creada")

solicitud = re.search(r"Solicitud #(\d+)", r.text)
sid = int(solicitud.group(1)) if solicitud else 1
cita = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT09:00")
r = s.post(f"{BASE}/solicitudes/{sid}/asignar", data={"medico_id": 1, "fecha_asignada": cita})
revisar("asignada a" in r.text, "solicitud asignada")

r = s.post(f"{BASE}/solicitudes/{sid}/visita", data={"tarifa_consulta_id": 2})
revisar("Visita medica" in r.text, "visita abierta con su cargo de consulta")
visita = re.search(r"/visitas/(\d+)", r.url or "")
vid = int(visita.group(1)) if visita else 1

s.post(f"{BASE}/visitas/{vid}/diagnostico",
       data={"diagnostico": "Hipertension arterial", "observaciones": "Control en 30 dias"})
r = s.post(f"{BASE}/visitas/{vid}/examenes", data={"tarifa_id": 4, "indicaciones": "En ayunas"})
revisar("Examen solicitado" in r.text, "examen solicitado con su cargo")

r = s.post(f"{BASE}/visitas/{vid}/recetas",
           data={"tarifa_id": 6, "cantidad": 30, "indicaciones": "1 cada 24 horas"})
revisar("Medicamento indicado" in r.text, "medicamento recetado")

examen = re.search(r'/examenes/(\d+)/resultado', s.get(f"{BASE}/laboratorio").text)
if examen:
    r = s.post(f"{BASE}/examenes/{examen.group(1)}/resultado",
               data={"resultado": "Colesterol 232 mg/dL"})
    revisar("Resultado cargado" in r.text, "resultado cargado")

receta = re.search(r'/recetas/(\d+)/entregar', s.get(f"{BASE}/farmacia").text)
if receta:
    r = s.post(f"{BASE}/recetas/{receta.group(1)}/entregar")
    revisar("Medicamento entregado" in r.text, "medicamento entregado con su cargo")

# ------------------------------------------------------------------- caja
caja = entrar("caja", "Asilo2026*")
r = caja.get(f"{BASE}/caja")
revisar(r.status_code == 200 and "Cuotas mensuales" in r.text, "caja abre su modulo")

r = caja.post(f"{BASE}/caja/donaciones", data={
    "origen": "EMPRESA_NACIONAL", "donante": "Distribuidora La Esperanza",
    "monto": "5000", "fecha": date.today().isoformat(),
    "descripcion": "Aporte trimestral", "recibo": "A-1201"})
revisar("Donacion registrada" in r.text, "donacion registrada")

r = caja.post(f"{BASE}/caja/donaciones", data={
    "origen": "GOBIERNO", "donante": "Municipalidad de Mazatenango",
    "monto": "3500", "fecha": date.today().isoformat(), "descripcion": "Aporte municipal"})
revisar("Donacion registrada" in r.text, "segunda donacion registrada")

r = caja.post(f"{BASE}/caja/donaciones", data={
    "origen": "PARTICULAR", "donante": "Anonimo", "monto": "-50"})
revisar("mayor que cero" in r.text, "rechaza un monto negativo")

r = caja.post(f"{BASE}/caja/gastos", data={
    "categoria": "ENERGIA_ELECTRICA", "descripcion": "Energia electrica de agosto",
    "monto": "1250.75", "fecha": date.today().isoformat(), "comprobante": "EEGSA-88"})
revisar("Gasto registrado" in r.text, "gasto registrado")

r = caja.post(f"{BASE}/caja/gastos", data={
    "categoria": "AGUA", "descripcion": "Servicio de agua de agosto", "monto": "340"})
revisar("Gasto registrado" in r.text, "segundo gasto registrado")

hoy = date.today()
r = caja.post(f"{BASE}/caja/cuotas", data={"anio": hoy.year, "mes": hoy.month})
revisar("Se generaron" in r.text, "cuotas del mes generadas")

r = caja.post(f"{BASE}/caja/cuotas", data={"anio": hoy.year, "mes": hoy.month})
revisar("ya estaban generadas" in r.text, "no duplica las cuotas del mes")

cuota = re.search(r'/cuotas/(\d+)/cobrar', caja.get(f"{BASE}/caja").text)
if cuota:
    r = caja.post(f"{BASE}/cuotas/{cuota.group(1)}/cobrar",
                  data={"anio": hoy.year, "mes": hoy.month})
    revisar("Cuota cobrada" in r.text, "cuota cobrada")
    r = caja.post(f"{BASE}/cuotas/{cuota.group(1)}/cobrar",
                  data={"anio": hoy.year, "mes": hoy.month})
    revisar("ya fue cobrada" in r.text, "no cobra dos veces la misma cuota")

# --------------------------------------------------------------- reportes
r = caja.get(f"{BASE}/reportes")
revisar("Pagos a la fundacion" in r.text, "caja ve sus reportes")
revisar("Analisis medico" not in r.text, "caja no ve el reporte clinico ajeno a su rol")

pruebas_reportes = [
    ("costos-por-cita", "?paciente_id=1", ["Informe de costos por cita", "Total de la cita"]),
    ("analisis-medico", "?paciente_id=1", ["analisis medico", "Ficha medica"]),
    ("cobros-por-paciente", "?paciente_id=1", ["Reporte de cobros", "Saldo pendiente"]),
    ("pagos-fundacion", "", ["pagos a la fundacion", "Deuda actual"]),
    ("entradas", "", ["donaciones y cobros", "Total de entradas"]),
    ("examenes-por-paciente", "?paciente_id=1", ["examenes medicos", "Con resultado"]),
    ("medicamentos-por-paciente", "?paciente_id=1", ["medicamentos aplicados", "Entregados"]),
]

admin = entrar("admin", "Admin2026*")
for clave, filtro, esperados in pruebas_reportes:
    r = admin.get(f"{BASE}/reportes/{clave}{filtro}")
    ok = r.status_code == 200 and all(t.lower() in r.text.lower() for t in esperados)
    revisar(ok, f"reporte {clave}")

# Cifras concretas
r = admin.get(f"{BASE}/reportes/costos-por-cita?paciente_id=1")
revisar("Q227.50" in r.text, "el costo de la consulta aplica el 35% de descuento")
revisar("Q110.00" in r.text, "el examen aplica el 45% de descuento")

r = admin.get(f"{BASE}/reportes/entradas")
revisar("Q8,500.00" in r.text, "las entradas suman las dos donaciones")
revisar("Q1,590.75" in r.text, "los gastos del periodo se totalizan")

r = admin.get(f"{BASE}/reportes/pagos-fundacion")
revisar("Consulta" in r.text and "Examen" in r.text and "Medicamento" in r.text,
        "los pagos a la fundacion se agrupan por tipo de servicio")

# Filtro por rango de fechas
manana = (hoy + timedelta(days=1)).isoformat()
r = admin.get(f"{BASE}/reportes/cobros-por-paciente?paciente_id=1&desde={manana}")
revisar("No hay informacion" in r.text, "el filtro por fecha descarta lo anterior al rango")

# Un rol sin permiso no entra al reporte financiero
lab = entrar("laboratorio", "Asilo2026*")
r = lab.get(f"{BASE}/reportes/pagos-fundacion", allow_redirects=True)
revisar("no tiene permiso" in r.text, "laboratorio no puede ver los pagos a la fundacion")

print("\n=========================")
print("Sin fallos." if not fallos else f"{len(fallos)} FALLOS: " + "; ".join(fallos))
