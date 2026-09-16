"""Recorre el flujo completo con un navegador y toma capturas."""
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
IMG = Path("/home/claude/pruebas/img")
IMG.mkdir(exist_ok=True)
fallos = []


def foto(pg, nombre):
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(IMG / f"{nombre}.png"), full_page=True)


def revisar(pg, texto_esperado, paso):
    if texto_esperado not in pg.content():
        fallos.append(f"{paso}: no aparecio '{texto_esperado}'")
        print(f"  FALLO en {paso}")
    else:
        print(f"  ok  {paso}")


with sync_playwright() as p:
    navegador = p.chromium.launch()
    pg = navegador.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
    pg.set_default_timeout(8000)

    V = Path("/home/claude/vendor/node_modules/bootstrap/dist")
    CSS = (V / "css/bootstrap.min.css").read_text()
    JS = (V / "js/bootstrap.bundle.min.js").read_text()
    pg.route("**/*bootstrap*", lambda r: r.fulfill(
        body=CSS if ".css" in r.request.url else JS,
        content_type="text/css" if ".css" in r.request.url else "application/javascript"))

    # 1. Panel
    pg.goto(BASE)
    revisar(pg, "Internos activos", "panel inicial")
    foto(pg, "01_panel")

    # 2. Alta de un interno nuevo
    pg.goto(f"{BASE}/pacientes")
    revisar(pg, "Rosa Elvira Perez", "listado de internos")
    pg.fill("input[name=nombre]", "Elena Marroquin Sical")
    pg.fill("input[name=edad]", "84")
    pg.fill("textarea[name=motivo_ingreso]", "Sin red familiar de apoyo cercana.")
    pg.fill("input[name=familiar_nombre]", "Sofia Marroquin")
    pg.fill("input[name=correo_familiar]", "sofia.marroquin@ejemplo.com")
    pg.fill("input[name=telefono_familiar]", "5566-7788")
    pg.fill("input[name=cuota_mensual]", "800")
    pg.fill("input[name=psicopatologia]", "Ansiedad generalizada.")
    pg.fill("textarea[name=padecimientos]", "Hipotiroidismo controlado.")
    foto(pg, "02_alta_interno")
    pg.click("button:has-text('Registrar interno')")
    revisar(pg, "Interno registrado", "alta de interno")
    revisar(pg, "Elena Marroquin Sical", "expediente del nuevo interno")

    # 3. Ficha medica y medicamento permanente
    pg.fill("textarea[name=alergias]", "Ninguna conocida.")
    pg.click("button:has-text('Guardar ficha')")
    revisar(pg, "Ficha medica actualizada", "guardar ficha")

    pg.fill("input[placeholder=Medicamento]", "Levotiroxina 50mcg")
    pg.fill("input[placeholder=Dosis]", "1 tableta")
    pg.fill("input[placeholder=Frecuencia]", "Cada 24 horas")
    pg.click("form[action$='/medicamentos'] button")
    revisar(pg, "Levotiroxina", "medicamento permanente")

    # 4. Referencia a especialidad
    pg.select_option("select[name=especialidad_id]", label="Cardiologia")
    pg.select_option("select[name=enfermero_id]", index=1)
    pg.fill("textarea[name=motivo]", "Presion arterial elevada en la evaluacion del medico general.")
    pg.click("button:has-text('Crear solicitud')")
    revisar(pg, "enviada a la fundacion", "crear solicitud")
    revisar(pg, "Correos enviados al familiar", "bitacora de correos")
    foto(pg, "03_expediente_con_solicitud")

    # 5. Modulo de la fundacion: asignar medico y horario
    pg.goto(f"{BASE}/fundacion")
    revisar(pg, "Elena Marroquin Sical", "bandeja de la fundacion")
    cita = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT09:30")
    pg.fill("input[name=fecha_asignada]", cita)
    foto(pg, "04_fundacion_pendiente")
    pg.click("button:has-text('Asignar')")
    revisar(pg, "asignada a", "asignacion de medico y horario")
    pg.goto(f"{BASE}/fundacion?estado=ASIGNADA")
    revisar(pg, "Convertir en visita", "solicitud lista para atender")
    foto(pg, "05_fundacion_asignada")

    # 6. Convertir la solicitud en visita medica (genera el cargo de consulta)
    pg.select_option("select[name=tarifa_consulta_id]", index=1)
    pg.click("button:has-text('Convertir en visita')")
    revisar(pg, "Visita medica", "apertura de visita")
    foto(pg, "06_visita_abierta")

    # 7. Diagnostico
    pg.fill("textarea[name=diagnostico]", "Hipertension arterial no controlada.")
    pg.fill("textarea[name=observaciones]", "Se ajusta tratamiento y se solicita control en 30 dias.")
    pg.click("button:has-text('Guardar')")
    revisar(pg, "Diagnostico y observaciones guardados", "guardar diagnostico")

    # 8. Examen de laboratorio
    pg.select_option("form[action$='/examenes'] select[name=tarifa_id]", index=1)
    pg.fill("input[name=indicaciones]", "En ayunas de 12 horas")
    pg.click("form[action$='/examenes'] button")
    revisar(pg, "Examen solicitado", "orden de examen")

    # 9. Medicamento recetado
    pg.select_option("form[action$='/recetas'] select[name=tarifa_id]", index=0)
    pg.fill("form[action$='/recetas'] input[name=cantidad]", "30")
    pg.fill("form[action$='/recetas'] input[name=indicaciones]", "1 tableta cada 24 horas")
    pg.click("form[action$='/recetas'] button")
    revisar(pg, "Medicamento indicado", "receta")
    foto(pg, "07_visita_completa")

    # 10. Laboratorio carga el resultado
    pg.goto(f"{BASE}/laboratorio")
    revisar(pg, "Perfil lipidico", "bandeja de laboratorio")
    pg.fill("textarea[name=resultado]",
            "Colesterol total 232 mg/dL, LDL 158 mg/dL, trigliceridos 190 mg/dL.")
    foto(pg, "08_laboratorio")
    pg.click("button:has-text('Cargar resultado')")
    revisar(pg, "Resultado cargado", "carga de resultado")

    # 11. Farmacia entrega y cobra
    pg.goto(f"{BASE}/farmacia")
    revisar(pg, "Losartan", "bandeja de farmacia")
    foto(pg, "09_farmacia")
    pg.click("button:has-text('Entregar y cobrar')")
    revisar(pg, "Medicamento entregado", "entrega de medicamento")

    # 12. Expediente final: historial y cuenta
    pg.goto(f"{BASE}/pacientes")
    pg.click("a:has-text('Abrir') >> nth=1")
    if "Elena" not in pg.content():
        pg.goto(f"{BASE}/pacientes")
        pg.click("tr:has-text('Elena Marroquin Sical') a:has-text('Abrir')")
    revisar(pg, "Historial medico", "historial")
    revisar(pg, "Saldo pendiente", "estado de cuenta")
    revisar(pg, "Perfil lipidico", "examen en el historial")
    foto(pg, "10_expediente_final")

    # 13. Cerrar la visita
    pg.goto(f"{BASE}/fundacion?estado=ATENDIDA")
    pg.click("a:has-text('Ver visita')")
    pg.click("button:has-text('Cerrar visita')")
    pg.wait_for_timeout(600)
    pg.click("#modalCerrar button:has-text('Si, cerrar visita')")
    pg.wait_for_load_state("networkidle")
    revisar(pg, "Visita medica cerrada", "cierre de visita")
    foto(pg, "11_visita_cerrada")

    navegador.close()

print("\n=========================")
if fallos:
    print(f"{len(fallos)} FALLOS:")
    for f in fallos:
        print(" -", f)
else:
    print("Flujo completo sin fallos.")
