"""
CAPA DE LOGICA DE NEGOCIO - REPORTES

Genera los siete informes que pide el enunciado. Cada metodo devuelve una
estructura uniforme (titulo, columnas, filas, totales) que la capa de
presentacion sabe dibujar, de modo que un reporte nuevo no obliga a crear una
pantalla nueva.

Los datos clinicos salen de db_asilo y los cobros de ms-costos, que es quien
aplica el descuento de la fundacion.
"""
from datetime import date, datetime

from clientes import MicroservicioError
from models import ETIQUETA_GASTO, ETIQUETA_ORIGEN, CategoriaGasto, OrigenDonacion
from repository import (
    CuotaRepository, DonacionRepository, ExamenRepository, GastoRepository,
    PacienteRepository, RecetaRepository, VisitaRepository,
)

MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def quetzales(valor: float) -> str:
    return f"Q{valor:,.2f}"


def fecha_larga(valor) -> str:
    if isinstance(valor, str):          # viene de un microservicio en ISO
        return f"{valor[8:10]}/{valor[5:7]}/{valor[0:4]}"
    return valor.strftime("%d/%m/%Y")


def columna(texto: str, numerica: bool = False) -> dict:
    return {"texto": texto, "numerica": numerica}


class ReporteService:
    def __init__(self, sesion, cliente_costos):
        self.sesion = sesion
        self.costos = cliente_costos
        self.pacientes = PacienteRepository(sesion)
        self.visitas = VisitaRepository(sesion)
        self.examenes = ExamenRepository(sesion)
        self.recetas = RecetaRepository(sesion)
        self.donaciones = DonacionRepository(sesion)
        self.gastos = GastoRepository(sesion)
        self.cuotas = CuotaRepository(sesion)

    # ------------------------------------------------------------- apoyo
    def _cargos(self, paciente_id=None) -> list:
        try:
            return self.costos.listar_cargos(paciente_id)
        except MicroservicioError:
            return []

    @staticmethod
    def _en_rango(cargo: dict, desde, hasta) -> bool:
        fecha = cargo["fecha_registro"][:10]
        if desde and fecha < desde.isoformat():
            return False
        if hasta and fecha > hasta.isoformat():
            return False
        return True

    @staticmethod
    def _periodo(desde, hasta) -> str:
        if desde and hasta:
            return f"Del {fecha_larga(desde)} al {fecha_larga(hasta)}"
        if desde:
            return f"Desde el {fecha_larga(desde)}"
        if hasta:
            return f"Hasta el {fecha_larga(hasta)}"
        return "Todos los registros"

    # --------------------------------------------------- 1. costos por cita
    def costos_por_cita(self, paciente_id: int, desde=None, hasta=None) -> dict:
        """Costo de cada cita del interno, incluyendo examenes y medicamentos."""
        paciente = self.pacientes.obtener(paciente_id)
        cargos = [c for c in self._cargos(paciente_id) if self._en_rango(c, desde, hasta)]

        por_visita = {}
        for cargo in cargos:
            por_visita.setdefault(cargo.get("visita_id") or 0, []).append(cargo)

        filas, total_general, total_ahorro = [], 0.0, 0.0
        for visita in self.visitas.historial(paciente_id):
            propios = por_visita.pop(visita.id, [])
            if not propios and (desde or hasta):
                continue
            consulta = sum(c["total"] for c in propios if c["tipo_servicio"] == "CONSULTA")
            examen = sum(c["total"] for c in propios if c["tipo_servicio"] == "EXAMEN")
            medicina = sum(c["total"] for c in propios if c["tipo_servicio"] == "MEDICAMENTO")
            ahorro = sum(c["subtotal"] - c["total"] for c in propios)
            total = consulta + examen + medicina
            total_general += total
            total_ahorro += ahorro
            filas.append([
                f"#{visita.id}",
                fecha_larga(visita.fecha),
                f"{visita.medico.nombre} ({visita.medico.especialidad.nombre})",
                quetzales(consulta), quetzales(examen), quetzales(medicina),
                quetzales(ahorro), quetzales(total),
            ])

        sueltos = [c for grupo in por_visita.values() for c in grupo]
        if sueltos:
            total = sum(c["total"] for c in sueltos)
            total_general += total
            filas.append(["—", "—", "Cargos sin visita asociada", "—", "—", "—",
                          "—", quetzales(total)])

        return {
            "titulo": "Informe de costos por cita",
            "subtitulo": f"{paciente.nombre} · familiar responsable: {paciente.familiar_nombre}",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Visita"), columna("Fecha"), columna("Medico tratante"),
                         columna("Consulta", True), columna("Examenes", True),
                         columna("Medicamentos", True), columna("Ahorro fundacion", True),
                         columna("Total de la cita", True)],
            "filas": filas,
            "totales": [("Total de citas", str(len(filas))),
                        ("Ahorro otorgado por la fundacion", quetzales(total_ahorro)),
                        ("Total cargado al familiar", quetzales(total_general))],
            "nota": "El costo de cada cita incluye la consulta, los examenes de laboratorio "
                    "y los medicamentos entregados, ya con el descuento de la fundacion.",
        }

    # ----------------------------------------------- 2. analisis medico
    def analisis_medico(self, paciente_id: int) -> dict:
        """Ficha medica del interno: por que fue recluido, padecimientos y medicamentos."""
        paciente = self.pacientes.obtener(paciente_id)
        historial = self.visitas.historial(paciente_id)

        diagnosticos = [
            {"fecha": fecha_larga(v.fecha),
             "medico": f"{v.medico.nombre} ({v.medico.especialidad.nombre})",
             "motivo": v.motivo,
             "diagnostico": v.diagnostico or "Sin diagnostico registrado",
             "observaciones": v.observaciones or "—",
             "examenes": [(e.nombre, e.resultado or "Sin resultado") for e in v.examenes],
             "medicamentos": [(r.nombre, r.cantidad, r.indicaciones or "—", r.entregado)
                              for r in v.recetas]}
            for v in historial
        ]
        return {
            "titulo": "Reporte de analisis medico por paciente",
            "paciente": paciente,
            "diagnosticos": diagnosticos,
            "generado": datetime.now(),
        }

    # ------------------------------------------- 3. cobros por rango de fecha
    def cobros_por_paciente(self, paciente_id: int, desde=None, hasta=None) -> dict:
        """Cobros del interno en un rango de fechas, con el detalle de cada gasto medico."""
        paciente = self.pacientes.obtener(paciente_id)
        cargos = sorted(
            [c for c in self._cargos(paciente_id) if self._en_rango(c, desde, hasta)],
            key=lambda c: c["fecha_registro"])

        filas, facturado, pagado = [], 0.0, 0.0
        for c in cargos:
            facturado += c["total"]
            if c["estado"] == "PAGADO":
                pagado += c["total"]
            filas.append([
                fecha_larga(c["fecha_registro"]),
                c["tipo_servicio"].capitalize(),
                c["descripcion"],
                str(c["cantidad"]),
                quetzales(c["subtotal"]),
                f"{c['descuento_aplicado']:.0f}%",
                quetzales(c["total"]),
                "Pagado" if c["estado"] == "PAGADO" else "Pendiente",
            ])

        return {
            "titulo": "Reporte de cobros por paciente",
            "subtitulo": f"{paciente.nombre} · cuenta de {paciente.familiar_nombre}",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Fecha"), columna("Tipo"), columna("Detalle del gasto medico"),
                         columna("Cantidad", True), columna("Subtotal", True),
                         columna("Descuento", True), columna("Total", True), columna("Estado")],
            "filas": filas,
            "totales": [("Cargos en el periodo", str(len(filas))),
                        ("Total facturado", quetzales(facturado)),
                        ("Cobrado", quetzales(pagado)),
                        ("Saldo pendiente", quetzales(facturado - pagado))],
            "nota": "Cada linea es un gasto medico cargado a la cuenta del familiar.",
        }

    # ------------------------------------------------ 4. pagos a la fundacion
    def pagos_a_la_fundacion(self, desde=None, hasta=None) -> dict:
        """Lo que el asilo debe y ha pagado a la fundacion por sus servicios."""
        cargos = [c for c in self._cargos() if self._en_rango(c, desde, hasta)]

        resumen = {}
        for c in cargos:
            tipo = c["tipo_servicio"]
            datos = resumen.setdefault(tipo, {"cantidad": 0, "sin_descuento": 0.0,
                                              "total": 0.0, "pagado": 0.0})
            datos["cantidad"] += 1
            datos["sin_descuento"] += c["subtotal"]
            datos["total"] += c["total"]
            if c["estado"] == "PAGADO":
                datos["pagado"] += c["total"]

        filas, total, pagado, ahorro = [], 0.0, 0.0, 0.0
        for tipo, d in sorted(resumen.items()):
            total += d["total"]
            pagado += d["pagado"]
            ahorro += d["sin_descuento"] - d["total"]
            filas.append([
                tipo.capitalize(), str(d["cantidad"]),
                quetzales(d["sin_descuento"]),
                quetzales(d["sin_descuento"] - d["total"]),
                quetzales(d["total"]), quetzales(d["pagado"]),
                quetzales(d["total"] - d["pagado"]),
            ])

        return {
            "titulo": "Reporte de pagos a la fundacion",
            "subtitulo": "Servicios prestados por la fundacion a los internos del asilo",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Tipo de servicio"), columna("Cantidad", True),
                         columna("Precio de lista", True), columna("Descuento otorgado", True),
                         columna("Total a la fundacion", True), columna("Pagado", True),
                         columna("Pendiente de pago", True)],
            "filas": filas,
            "totales": [("Ahorro total por el convenio", quetzales(ahorro)),
                        ("Total facturado por la fundacion", quetzales(total)),
                        ("Pagado a la fundacion", quetzales(pagado)),
                        ("Deuda actual con la fundacion", quetzales(total - pagado))],
            "nota": "La deuda con la fundacion corresponde a los cargos que aun no han "
                    "sido cancelados por los familiares.",
        }

    # ------------------------------------------------------- 5. entradas
    def entradas(self, desde=None, hasta=None) -> dict:
        """Donaciones, cuotas de familiares y cobros recibidos, frente a los gastos."""
        filas = []

        total_donaciones = 0.0
        for origen, monto, cantidad in self.donaciones.total_por_origen(desde, hasta):
            total_donaciones += float(monto)
            filas.append(["Donacion", ETIQUETA_ORIGEN.get(origen, str(origen)),
                          str(cantidad), quetzales(float(monto))])

        cuotas = [c for c in self.cuotas.listar()
                  if c.pagada and self._fecha_en_rango(c.fecha_pago, desde, hasta)]
        total_cuotas = sum(c.monto for c in cuotas)
        if cuotas:
            filas.append(["Cuota mensual", "Familiares de los internos",
                          str(len(cuotas)), quetzales(total_cuotas)])

        cargos = [c for c in self._cargos()
                  if c["estado"] == "PAGADO" and self._en_rango(c, desde, hasta)]
        total_cobros = sum(c["total"] for c in cargos)
        if cargos:
            filas.append(["Cobro de servicios medicos", "Familiares de los internos",
                          str(len(cargos)), quetzales(total_cobros)])

        total_gastos = self.gastos.total(desde, hasta)
        total_entradas = total_donaciones + total_cuotas + total_cobros

        return {
            "titulo": "Reporte de entradas: donaciones y cobros",
            "subtitulo": "Ingresos del asilo y su comparacion con los gastos del periodo",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Concepto"), columna("Origen"),
                         columna("Movimientos", True), columna("Monto", True)],
            "filas": filas,
            "totales": [("Total de donaciones", quetzales(total_donaciones)),
                        ("Total de cuotas cobradas", quetzales(total_cuotas)),
                        ("Total de cobros por servicios", quetzales(total_cobros)),
                        ("Total de entradas", quetzales(total_entradas)),
                        ("Total de gastos del periodo", quetzales(total_gastos)),
                        ("Diferencia", quetzales(total_entradas - total_gastos))],
            "nota": "El asilo se sostiene con donaciones y con la cuota mensual que pagan "
                    "los familiares. Esta comparacion permite fiscalizar el periodo.",
        }

    @staticmethod
    def _fecha_en_rango(momento, desde, hasta) -> bool:
        if momento is None:
            return False
        dia = momento.date() if isinstance(momento, datetime) else momento
        if desde and dia < desde:
            return False
        if hasta and dia > hasta:
            return False
        return True

    # ------------------------------------------------ 6. examenes por paciente
    def examenes_por_paciente(self, paciente_id: int, desde=None, hasta=None) -> dict:
        paciente = self.pacientes.obtener(paciente_id)
        cargos = {c.get("visita_id"): c for c in self._cargos(paciente_id)
                  if c["tipo_servicio"] == "EXAMEN"}

        filas, con_resultado = [], 0
        for visita in self.visitas.historial(paciente_id):
            for examen in visita.examenes:
                if not self._fecha_en_rango(examen.fecha_solicitud, desde, hasta):
                    continue
                listo = examen.estado.value == "CON_RESULTADO"
                con_resultado += 1 if listo else 0
                filas.append([
                    fecha_larga(examen.fecha_solicitud),
                    f"#{visita.id}",
                    examen.nombre,
                    visita.medico.nombre,
                    examen.resultado or "Pendiente de resultado",
                    "Con resultado" if listo else "En laboratorio",
                ])

        return {
            "titulo": "Reporte de examenes medicos realizados",
            "subtitulo": f"{paciente.nombre}",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Fecha"), columna("Visita"), columna("Examen"),
                         columna("Solicitado por"), columna("Resultado"), columna("Estado")],
            "filas": filas,
            "totales": [("Examenes solicitados", str(len(filas))),
                        ("Con resultado cargado", str(con_resultado)),
                        ("Pendientes", str(len(filas) - con_resultado))],
            "nota": "Incluye los examenes solicitados en todas las visitas medicas del interno.",
        }

    # -------------------------------------------- 7. medicamentos por paciente
    def medicamentos_por_paciente(self, paciente_id: int, desde=None, hasta=None) -> dict:
        paciente = self.pacientes.obtener(paciente_id)

        filas, entregados = [], 0
        for visita in self.visitas.historial(paciente_id):
            for receta in visita.recetas:
                if not self._fecha_en_rango(receta.fecha_receta, desde, hasta):
                    continue
                entregados += 1 if receta.entregado else 0
                filas.append([
                    fecha_larga(receta.fecha_receta),
                    f"#{visita.id}",
                    receta.nombre,
                    str(receta.cantidad),
                    receta.indicaciones or "—",
                    visita.medico.nombre,
                    "Entregado" if receta.entregado else "Pendiente en farmacia",
                ])

        permanentes = [(m.nombre, m.dosis, m.frecuencia)
                       for m in paciente.medicamentos_permanentes]

        return {
            "titulo": "Reporte de medicamentos aplicados",
            "subtitulo": f"{paciente.nombre}",
            "periodo": self._periodo(desde, hasta),
            "columnas": [columna("Fecha"), columna("Visita"), columna("Medicamento"),
                         columna("Cantidad", True), columna("Como tomarlo"),
                         columna("Indicado por"), columna("Estado")],
            "filas": filas,
            "totales": [("Medicamentos indicados", str(len(filas))),
                        ("Entregados por farmacia", str(entregados)),
                        ("Pendientes de entrega", str(len(filas) - entregados))],
            "nota": "Medicamentos permanentes del interno: " + (
                "; ".join(f"{n} ({d}, {f})" for n, d, f in permanentes)
                if permanentes else "ninguno registrado."),
        }
