"""RNF-20 y RNF-21. Correr despues de plan_pruebas.py (usa sus contrasenas).

Uso:
  python pruebas/carga.py carga --usuarios 20 --segundos 60
  python pruebas/carga.py volumen --cargos 5000
"""
import argparse
import os
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests

BASE = os.getenv("BASE", "http://localhost:8000")
URL_COSTOS = os.getenv("URL_MS_COSTOS", "http://localhost:8001")
API_KEY = os.getenv("API_KEY_SERVICIOS", "")

RECORRIDOS = {
    "caja": ["/", "/pacientes", "/pacientes/1", "/caja", "/reportes/entradas"],
    "mgeneral": ["/", "/pacientes", "/pacientes/2", "/reportes/analisis-medico?paciente_id=1"],
    "fundacion": ["/", "/fundacion", "/fundacion?estado=ASIGNADA"],
    "laboratorio": ["/", "/laboratorio"],
    "farmacia": ["/", "/farmacia"],
}


def entrar(usuario):
    s = requests.Session()
    s.post(f"{BASE}/login", data={"usuario": usuario, "contrasena": f"Prueba{usuario}2026x"})
    return s


def percentil(valores, p):
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(len(ordenados) * p))]


def carga(usuarios, segundos):
    # Hay una sola sesion vigente por usuario: los hilos de un rol comparten su cookie.
    nombres = list(RECORRIDOS)
    cookies = {rol: entrar(rol).cookies for rol in nombres}
    sesiones = []
    for i in range(usuarios):
        rol = nombres[i % len(nombres)]
        s = requests.Session()
        s.cookies.update(cookies[rol])
        sesiones.append((rol, s))
    tiempos, errores, candado = [], 0, threading.Lock()
    fin = time.time() + segundos

    def trabajar(rol, sesion):
        nonlocal errores
        while time.time() < fin:
            for ruta in RECORRIDOS[rol]:
                inicio = time.perf_counter()
                try:
                    r = sesion.get(BASE + ruta, timeout=30)
                    ok = r.status_code == 200 and "/login" not in r.url
                except requests.RequestException:
                    ok = False
                duracion = time.perf_counter() - inicio
                with candado:
                    tiempos.append(duracion)
                    if not ok:
                        errores += 1

    with ThreadPoolExecutor(max_workers=usuarios) as grupo:
        for rol, sesion in sesiones:
            grupo.submit(trabajar, rol, sesion)

    return {
        "usuarios": usuarios, "segundos": segundos, "peticiones": len(tiempos),
        "por_segundo": len(tiempos) / segundos, "errores": errores,
        "promedio_ms": statistics.mean(tiempos) * 1000,
        "p95_ms": percentil(tiempos, 0.95) * 1000, "maximo_ms": max(tiempos) * 1000,
    }


def volumen(cantidad):
    cabecera = {"X-API-Key": API_KEY}
    tarifas = requests.get(f"{URL_COSTOS}/tarifas?solo_activas=true", headers=cabecera).json()
    ids = [t["id"] for t in tarifas]
    inicio = time.perf_counter()

    def crear(i):
        requests.post(f"{URL_COSTOS}/cargos", headers=cabecera, timeout=30, json={
            "paciente_id": 1 + i % 3, "paciente_nombre": "Interno de volumen",
            "tarifa_id": ids[i % len(ids)], "cantidad": 1 + i % 5})

    with ThreadPoolExecutor(max_workers=10) as grupo:
        list(grupo.map(crear, range(cantidad)))
    carga_s = time.perf_counter() - inicio

    caja = entrar("caja")
    medidas = {}
    for nombre, ruta in [("Estado de cuenta (expediente)", "/pacientes/1"),
                         ("Reporte de pagos a la fundación", "/reportes/pagos-fundacion"),
                         ("Reporte de entradas", "/reportes/entradas"),
                         ("Reporte de cobros por paciente", "/reportes/cobros-por-paciente?paciente_id=1"),
                         ("Pantalla de caja", "/caja")]:
        inicio = time.perf_counter()
        r = caja.get(BASE + ruta, timeout=60)
        medidas[nombre] = ((time.perf_counter() - inicio) * 1000, r.status_code)
    total = len(requests.get(f"{URL_COSTOS}/cargos", headers=cabecera).json())
    return {"cargos_creados": cantidad, "cargos_totales": total, "segundos_creacion": carga_s,
            "medidas": medidas}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("modo", choices=["carga", "volumen"])
    p.add_argument("--usuarios", type=int, default=20)
    p.add_argument("--segundos", type=int, default=60)
    p.add_argument("--cargos", type=int, default=5000)
    a = p.parse_args()
    carpeta = Path(__file__).parent / "resultados"
    carpeta.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y-%m-%d_%H%M")

    if a.modo == "carga":
        r = carga(a.usuarios, a.segundos)
        lineas = [f"# Prueba de carga ({datetime.now():%d/%m/%Y %H:%M})", "",
                  f"- Usuarios simultáneos: {r['usuarios']}", f"- Duración: {r['segundos']} s",
                  f"- Peticiones: {r['peticiones']} ({r['por_segundo']:.1f} por segundo)",
                  f"- Errores: {r['errores']}", f"- Tiempo promedio: {r['promedio_ms']:.0f} ms",
                  f"- Percentil 95: {r['p95_ms']:.0f} ms", f"- Máximo: {r['maximo_ms']:.0f} ms"]
    else:
        r = volumen(a.cargos)
        lineas = [f"# Prueba de volumen ({datetime.now():%d/%m/%Y %H:%M})", "",
                  f"- Cargos creados: {r['cargos_creados']} en {r['segundos_creacion']:.0f} s",
                  f"- Cargos totales en db_costos: {r['cargos_totales']}", "",
                  "| Pantalla | Tiempo | HTTP |", "|---|---|---|"]
        lineas += [f"| {k} | {v[0]:.0f} ms | {v[1]} |" for k, v in r["medidas"].items()]
    texto = "\n".join(lineas) + "\n"
    (carpeta / f"{a.modo}_{marca}.md").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
