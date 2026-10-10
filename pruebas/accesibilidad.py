"""
REVISION DE ACCESIBILIDAD WCAG 2.1 NIVEL AA (RNF-22)

Abre cada pantalla en un navegador real (Chromium, con Playwright) y ejecuta
axe-core, la herramienta de revision automatica de accesibilidad mas usada.
Reporta las violaciones de las reglas WCAG 2.0/2.1 A y AA por pantalla.

Requisitos:
  pip install playwright && playwright install chromium
  Archivo axe.min.js (npm install axe-core) indicado en AXE_JS.
  Ejecutar despues de plan_pruebas.py (usa la contrasena PruebaAdmin2026x que deja ese plan).

Uso:
  AXE_JS=node_modules/axe-core/axe.min.js python pruebas/accesibilidad.py
"""
import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("BASE", "http://localhost:8000")
AXE = Path(os.getenv("AXE_JS", "node_modules/axe-core/axe.min.js")).read_text()
# Si el equipo no tiene salida a internet, Bootstrap se sirve desde una copia local.
BOOTSTRAP = os.getenv("BOOTSTRAP_LOCAL")

PANTALLAS = [
    ("Ingreso", "/login", None),
    ("Panel", "/", "admin"),
    ("Internos", "/pacientes", "admin"),
    ("Expediente", "/pacientes/1", "admin"),
    ("Solicitudes (fundacion)", "/fundacion?estado=ATENDIDA", "admin"),
    ("Laboratorio", "/laboratorio", "admin"),
    ("Farmacia", "/farmacia", "admin"),
    ("Caja", "/caja", "admin"),
    ("Visita medica", "/visitas/1", "admin"),
    ("Reportes", "/reportes", "admin"),
    ("Reporte de analisis medico", "/reportes/analisis-medico?paciente_id=1", "admin"),
    ("Reporte de entradas", "/reportes/entradas", "admin"),
    ("Bitacora", "/bitacora", "admin"),
    ("Cambiar contrasena", "/cuenta/contrasena", "admin"),
]


def preparar(pagina):
    if not BOOTSTRAP:
        return
    css = (Path(BOOTSTRAP) / "css/bootstrap.min.css").read_text()
    js = (Path(BOOTSTRAP) / "js/bootstrap.bundle.min.js").read_text()
    pagina.route("**/*bootstrap*", lambda r: r.fulfill(
        body=css if ".css" in r.request.url else js,
        content_type="text/css" if ".css" in r.request.url else "application/javascript"))
    pagina.route("**/fonts.googleapis.com/**", lambda r: r.fulfill(body="", content_type="text/css"))


def main():
    filas, total = [], 0
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1366, "height": 900})
        preparar(pagina)
        dentro = False
        for nombre, ruta, usuario in PANTALLAS:
            if usuario and not dentro:
                pagina.goto(f"{BASE}/login")
                pagina.fill("#usuario", usuario)
                pagina.fill("#contrasena",
                            "PruebaAdmin2026x" if usuario == "admin" else f"Prueba{usuario}2026x")
                pagina.click("button:has-text('Ingresar')")
                pagina.wait_for_load_state()
                dentro = True
            pagina.goto(BASE + ruta)
            pagina.add_script_tag(content=AXE)
            resultado = pagina.evaluate("""async () => {
                const r = await axe.run(document, {runOnly: {type: 'tag',
                    values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}});
                return r.violations.map(v => ({id: v.id, impacto: v.impact,
                    nodos: v.nodes.length, ayuda: v.help}));
            }""")
            total += len(resultado)
            filas.append((nombre, ruta, resultado))
            print(f"{nombre:28} {len(resultado)} violaciones")
            for v in resultado:
                print(f"   - [{v['impacto']}] {v['id']} ({v['nodos']}): {v['ayuda']}")
        navegador.close()

    lineas = [f"# Revision de accesibilidad WCAG 2.1 AA ({datetime.now():%d/%m/%Y %H:%M})", "",
              "Herramienta: axe-core en Chromium. Reglas: wcag2a, wcag2aa, wcag21a, wcag21aa.", "",
              "| Pantalla | Ruta | Violaciones | Detalle |", "|---|---|---|---|"]
    for nombre, ruta, res in filas:
        detalle = "; ".join(f"{v['id']} ({v['impacto']}, {v['nodos']})" for v in res) or "-"
        lineas.append(f"| {nombre} | {ruta} | {len(res)} | {detalle} |")
    carpeta = Path(__file__).parent / "resultados"
    carpeta.mkdir(exist_ok=True)
    (carpeta / f"accesibilidad_{datetime.now():%Y-%m-%d_%H%M}.md").write_text(
        "\n".join(lineas) + "\n", encoding="utf-8")
    print(f"\nTotal de violaciones: {total}")


if __name__ == "__main__":
    main()
