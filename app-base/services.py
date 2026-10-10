"""
CAPA DE LOGICA DE NEGOCIO  (aplicacion base)

Aqui viven las reglas del asilo descritas en el enunciado. Esta capa no sabe
que existe HTTP ni SQL: recibe datos, aplica reglas, usa los repositorios para
persistir y los clientes para hablar con los microservicios.

Reglas implementadas:
  - Un paciente no puede ser referido a especialidad si no tiene ficha medica.
  - La solicitud dispara el correo al familiar (requisito adicional del enunciado).
  - Solo la fundacion asigna medico y horario; sin eso no hay visita medica.
  - Una solicitud se convierte en visita medica una sola vez.
  - Cada consulta, examen y medicamento entregado genera un cargo a la cuenta
    del familiar, con el descuento de la fundacion, en el microservicio ms-costos.
  - El laboratorio solo carga resultados de examenes que fueron solicitados.
  - La farmacia solo cobra el medicamento cuando lo entrega.
  - Toda entrada se valida en el servidor (modulo validaciones, reglas RV-xx).
"""
from datetime import date, datetime
from decimal import Decimal

import validaciones as v
from validaciones import ErrorNegocio, ErrorValidacion  # noqa: F401  (se reexportan)

from clientes import ClienteCostos, ClienteNotificaciones, MicroservicioError
from models import (
    CategoriaGasto, CuotaMensual, Donacion, Enfermero, Especialidad, EstadoExamen,
    EstadoSolicitud, EstadoVisita, FichaMedica, Gasto, Medico,
    MedicamentoPermanente, MedicamentoRecetado, OrdenExamen, OrigenDonacion,
    Paciente, PagoFundacion, Solicitud, VisitaMedica,
)
from repository import (
    CatalogoRepository, CuotaRepository, DonacionRepository, ExamenRepository,
    FichaRepository, GastoRepository, MedicamentoPermanenteRepository,
    PacienteRepository, PagoFundacionRepository, RecetaRepository,
    SolicitudRepository, VisitaRepository, marcar_actualizada,
)

LARGO_CLINICO = 4000   # texto libre de ficha, diagnostico y resultados


# ---------------------------------------------------------------- Pacientes
class PacienteService:
    def __init__(self, sesion):
        self.pacientes = PacienteRepository(sesion)
        self.fichas = FichaRepository(sesion)
        self.medicamentos = MedicamentoPermanenteRepository(sesion)

    def listar(self):
        return self.pacientes.listar()

    def obtener(self, paciente_id: int) -> Paciente:
        paciente = self.pacientes.obtener(paciente_id)
        if paciente is None:
            raise ErrorNegocio("El interno indicado no existe.")
        return paciente

    @staticmethod
    def _datos_validos(datos: dict) -> dict:
        """Aplica las reglas RV-xx a los datos del interno (alta y edicion)."""
        return {
            "nombre": v.texto(datos.get("nombre"), "nombre del interno", minimo=3, maximo=120),
            "edad": v.entero(datos.get("edad"), "edad", v.EDAD_MINIMA, v.EDAD_MAXIMA),
            "fecha_ingreso": v.fecha(datos.get("fecha_ingreso"), "fecha de ingreso"),
            "motivo_ingreso": v.texto(datos.get("motivo_ingreso"), "motivo de ingreso",
                                      obligatorio=False, maximo=300),
            "familiar_nombre": v.texto(datos.get("familiar_nombre"), "nombre del familiar",
                                       minimo=3, maximo=120),
            "correo_familiar": v.correo(datos.get("correo_familiar")),
            "telefono_familiar": v.telefono(datos.get("telefono_familiar")),
            "cuota_mensual": v.monto(datos.get("cuota_mensual"), "cuota mensual",
                                     maximo=v.CUOTA_MAXIMA),
        }

    def registrar(self, datos: dict) -> Paciente:
        validos = self._datos_validos(datos)
        paciente = Paciente(**{**validos, "cuota_mensual": float(validos["cuota_mensual"])})

        # Todo interno nace con su ficha medica: sin ficha no puede ser atendido.
        paciente.ficha = FichaMedica(
            psicopatologia=v.texto(datos.get("psicopatologia"), "psicopatologia",
                                   obligatorio=False, maximo=LARGO_CLINICO),
            padecimientos=v.texto(datos.get("padecimientos"), "padecimientos",
                                  obligatorio=False, maximo=LARGO_CLINICO),
        )
        return self.pacientes.guardar(paciente)

    def actualizar(self, paciente_id: int, datos: dict) -> Paciente:
        paciente = self.obtener(paciente_id)
        # Los campos que no vienen en el formulario conservan su valor actual,
        # pero todo el conjunto se valida de nuevo antes de guardar.
        actuales = {
            "nombre": paciente.nombre, "edad": paciente.edad,
            "fecha_ingreso": paciente.fecha_ingreso.isoformat(),
            "motivo_ingreso": paciente.motivo_ingreso,
            "familiar_nombre": paciente.familiar_nombre,
            "correo_familiar": paciente.correo_familiar,
            "telefono_familiar": paciente.telefono_familiar,
            "cuota_mensual": f"{paciente.cuota_mensual:.2f}",
        }
        actuales.update({k: val for k, val in datos.items() if k in actuales})
        validos = self._datos_validos(actuales)
        for campo, valor in validos.items():
            setattr(paciente, campo, float(valor) if campo == "cuota_mensual" else valor)
        self.pacientes.confirmar()
        return paciente

    def dar_de_baja(self, paciente_id: int) -> Paciente:
        paciente = self.obtener(paciente_id)
        self.pacientes.eliminar(paciente)
        return paciente

    def actualizar_ficha(self, paciente_id: int, datos: dict) -> FichaMedica:
        paciente = self.obtener(paciente_id)
        ficha = paciente.ficha or FichaMedica(paciente_id=paciente.id)
        for campo in ("psicopatologia", "padecimientos", "alergias", "observaciones"):
            setattr(ficha, campo, v.texto(datos.get(campo), campo, obligatorio=False,
                                          maximo=LARGO_CLINICO))
        marcar_actualizada(ficha)
        return self.fichas.guardar(ficha)

    def agregar_medicamento_permanente(self, paciente_id: int, datos: dict):
        paciente = self.obtener(paciente_id)
        medicamento = MedicamentoPermanente(
            paciente_id=paciente.id,
            nombre=v.texto(datos.get("nombre"), "nombre del medicamento", maximo=120),
            dosis=v.texto(datos.get("dosis"), "dosis", obligatorio=False, maximo=80),
            frecuencia=v.texto(datos.get("frecuencia"), "frecuencia", obligatorio=False,
                               maximo=80),
        )
        return self.medicamentos.guardar(medicamento)

    def quitar_medicamento_permanente(self, medicamento_id: int):
        medicamento = self.medicamentos.obtener(medicamento_id)
        if medicamento is None:
            raise ErrorNegocio("El medicamento indicado no existe.")
        self.medicamentos.eliminar(medicamento)


# ------------------------------------------------------- Flujo de atencion
class AtencionService:
    """Solicitud -> asignacion de la fundacion -> visita -> examenes y recetas."""

    def __init__(self, sesion):
        self.sesion = sesion
        self.pacientes = PacienteRepository(sesion)
        self.catalogo = CatalogoRepository(sesion)
        self.solicitudes = SolicitudRepository(sesion)
        self.visitas = VisitaRepository(sesion)
        self.examenes = ExamenRepository(sesion)
        self.recetas = RecetaRepository(sesion)
        self.costos = ClienteCostos()
        self.notificaciones = ClienteNotificaciones()

    # ---------- 1. El medico general refiere al paciente ----------
    def crear_solicitud(self, datos: dict):
        """
        Regla del enunciado: el medico general evalua primero y determina a que
        especialidad se remite al paciente, asignando el enfermero que lo acompania.
        Devuelve (solicitud, advertencia_del_correo).
        """
        paciente = self.pacientes.obtener(v.entero(datos.get("paciente_id"), "interno", 1))
        if paciente is None or not paciente.activo:
            raise ErrorNegocio("El interno indicado no existe o fue dado de baja.")
        if paciente.ficha is None:
            raise ErrorNegocio(
                "El interno no tiene ficha medica. Complete la ficha antes de referirlo.")
        motivo = v.texto(datos.get("motivo"), "motivo de la referencia", minimo=3, maximo=300)

        especialidad_id = v.entero(datos.get("especialidad_id"), "especialidad", 1)
        if self.sesion.get(Especialidad, especialidad_id) is None:
            raise ErrorNegocio("La especialidad indicada no existe.")
        enfermero_id = None
        if datos.get("enfermero_id"):
            enfermero_id = v.entero(datos["enfermero_id"], "enfermero", 1)
            if self.sesion.get(Enfermero, enfermero_id) is None:
                raise ErrorNegocio("El enfermero indicado no existe.")

        solicitud = Solicitud(
            paciente_id=paciente.id,
            especialidad_id=especialidad_id,
            enfermero_id=enfermero_id,
            motivo=motivo,
            estado_paciente=v.texto(datos.get("estado_paciente"), "estado del paciente",
                                    obligatorio=False, maximo=80) or "Estable",
        )
        self.solicitudes.guardar(solicitud)
        solicitud = self.solicitudes.obtener(solicitud.id)

        advertencia = self._avisar_al_familiar(solicitud)
        return solicitud, advertencia

    def _avisar_al_familiar(self, solicitud: Solicitud,
                            tipo: str = "SOLICITUD_REGISTRADA") -> str | None:
        """
        Requisito adicional del enunciado: avisar por correo al familiar cuando se
        crea una solicitud, "informando el estado del paciente y a que medico fue
        referido". Se envian dos avisos:
          1. SOLICITUD_REGISTRADA: al crearse la solicitud (especialidad y motivo).
          2. MEDICO_ASIGNADO: cuando la fundacion asigna medico y horario, que es
             el momento en que el nombre del medico ya existe.
        Si el microservicio falla, la solicitud NO se pierde; por eso el correo
        esta separado del registro clinico.
        """
        try:
            self.notificaciones.notificar_solicitud({
                "tipo": tipo,
                "solicitud_id": solicitud.id,
                "fecha_cita": (solicitud.fecha_asignada.isoformat()
                               if solicitud.fecha_asignada else None),
                "paciente_id": solicitud.paciente.id,
                "paciente_nombre": solicitud.paciente.nombre,
                "familiar_nombre": solicitud.paciente.familiar_nombre,
                "correo_destino": solicitud.paciente.correo_familiar,
                "especialidad": solicitud.especialidad.nombre,
                "medico_asignado": solicitud.medico.nombre if solicitud.medico else None,
                "motivo": solicitud.motivo,
                "estado_paciente": solicitud.estado_paciente,
            })
            return None
        except MicroservicioError as error:
            return f"La solicitud se registro, pero no se pudo avisar al familiar. {error}"

    # ---------- 2. La fundacion asigna medico y horario ----------
    def asignar_solicitud(self, solicitud_id: int, datos: dict):
        """Devuelve (solicitud, advertencia_del_correo)."""
        solicitud = self._buscar_solicitud(solicitud_id)
        if solicitud.estado == EstadoSolicitud.ATENDIDA:
            raise ErrorNegocio("Esa solicitud ya fue atendida y no puede reasignarse.")

        medico = self.sesion.get(Medico, v.entero(datos.get("medico_id"), "medico", 1))
        if medico is None:
            raise ErrorNegocio("El medico indicado no existe.")
        if medico.especialidad_id != solicitud.especialidad_id:
            raise ErrorNegocio(
                f"{medico.nombre} no pertenece a la especialidad solicitada "
                f"({solicitud.especialidad.nombre}).")

        # Se asigna el objeto, no solo el id, para que la relacion quede cargada
        # y la vista pueda mostrar el nombre del medico sin volver a consultar.
        solicitud.medico = medico
        solicitud.fecha_asignada = v.fecha_hora_futura(datos.get("fecha_asignada"))
        solicitud.estado = EstadoSolicitud.ASIGNADA
        self.solicitudes.confirmar()

        advertencia = self._avisar_al_familiar(solicitud, "MEDICO_ASIGNADO")
        return solicitud, advertencia

    # ---------- 3. La solicitud se convierte en visita medica ----------
    def convertir_en_visita(self, solicitud_id: int, tarifa_consulta_id: int):
        """
        Regla del enunciado: "esta solicitud pasa a convertirse en visita medica".
        Al abrirse la visita se carga el costo de la consulta a la cuenta del
        familiar, con el descuento de la fundacion (microservicio ms-costos).
        """
        solicitud = self._buscar_solicitud(solicitud_id)
        if solicitud.estado == EstadoSolicitud.PENDIENTE:
            raise ErrorNegocio(
                "La fundacion aun no asigna medico ni horario a esta solicitud.")
        if solicitud.visita is not None:
            raise ErrorNegocio("Esta solicitud ya tiene una visita medica registrada.")
        if tarifa_consulta_id:
            # Se valida antes de crear la visita: una tarifa que no es de consulta
            # no debe dejar una visita a medio registrar.
            self._buscar_tarifa(int(tarifa_consulta_id), "CONSULTA")

        visita = VisitaMedica(
            solicitud_id=solicitud.id,
            paciente_id=solicitud.paciente_id,
            medico_id=solicitud.medico_id,
            motivo=solicitud.motivo,
        )
        self.visitas.guardar(visita)

        solicitud.estado = EstadoSolicitud.ATENDIDA
        self.solicitudes.confirmar()

        advertencia = None
        if tarifa_consulta_id:
            cargo, advertencia = self._cobrar(
                solicitud.paciente, int(tarifa_consulta_id), 1, visita.id)
            if cargo:
                visita.cargo_consulta_id = cargo["id"]
                self.visitas.confirmar()
        return visita, advertencia

    def registrar_diagnostico(self, visita_id: int, datos: dict) -> VisitaMedica:
        visita = self._buscar_visita(visita_id)
        if visita.estado == EstadoVisita.CERRADA:
            raise ErrorNegocio("La visita ya fue cerrada y no admite cambios.")
        visita.diagnostico = v.texto(datos.get("diagnostico"), "diagnostico",
                                     obligatorio=False, maximo=LARGO_CLINICO)
        visita.observaciones = v.texto(datos.get("observaciones"), "observaciones",
                                       obligatorio=False, maximo=LARGO_CLINICO)
        self.visitas.confirmar()
        return visita

    def cerrar_visita(self, visita_id: int) -> VisitaMedica:
        visita = self._buscar_visita(visita_id)
        if not visita.diagnostico.strip():
            raise ErrorNegocio("No se puede cerrar la visita sin registrar el diagnostico.")
        pendientes = [e for e in visita.examenes if e.estado == EstadoExamen.SOLICITADO]
        if pendientes:
            raise ErrorNegocio(
                f"Hay {len(pendientes)} examen(es) sin resultado. "
                "El laboratorio debe cargarlos antes de cerrar la visita.")
        visita.estado = EstadoVisita.CERRADA
        self.visitas.confirmar()
        return visita

    # ---------- 4. Examenes de laboratorio ----------
    def ordenar_examen(self, visita_id: int, datos: dict):
        visita = self._buscar_visita(visita_id)
        if visita.estado == EstadoVisita.CERRADA:
            raise ErrorNegocio("La visita esta cerrada: no admite examenes nuevos.")

        tarifa = self._buscar_tarifa(v.entero(datos.get("tarifa_id"), "examen", 1), "EXAMEN")
        examen = OrdenExamen(
            visita_id=visita.id,
            tarifa_id=tarifa["id"],
            nombre=tarifa["descripcion"],
            indicaciones=v.texto(datos.get("indicaciones"), "indicaciones",
                                 obligatorio=False, maximo=300),
        )
        self.examenes.guardar(examen)

        cargo, advertencia = self._cobrar(visita.paciente, tarifa["id"], 1, visita.id)
        if cargo:
            examen.cargo_id = cargo["id"]
            self.examenes.confirmar()
        return examen, advertencia

    def cargar_resultado(self, examen_id: int, resultado: str) -> OrdenExamen:
        examen = self.examenes.obtener(examen_id)
        if examen is None:
            raise ErrorNegocio("La orden de examen no existe.")
        if examen.estado == EstadoExamen.CON_RESULTADO:
            # El resultado es un dato clinico: no se sobrescribe sin dejar rastro.
            raise ErrorNegocio("Ese examen ya tiene resultado registrado.")
        examen.resultado = v.texto(resultado, "resultado del examen", maximo=LARGO_CLINICO)
        examen.estado = EstadoExamen.CON_RESULTADO
        examen.fecha_resultado = datetime.now()
        self.examenes.confirmar()
        return examen

    # ---------- 5. Farmacia ----------
    def recetar_medicamento(self, visita_id: int, datos: dict) -> MedicamentoRecetado:
        visita = self._buscar_visita(visita_id)
        if visita.estado == EstadoVisita.CERRADA:
            raise ErrorNegocio("La visita esta cerrada: no admite recetas nuevas.")

        tarifa = self._buscar_tarifa(v.entero(datos.get("tarifa_id"), "medicamento", 1),
                                     "MEDICAMENTO")
        cantidad = v.entero(datos.get("cantidad") or 1, "cantidad", 1, v.CANTIDAD_MAXIMA)

        receta = MedicamentoRecetado(
            visita_id=visita.id,
            tarifa_id=tarifa["id"],
            nombre=tarifa["descripcion"],
            cantidad=cantidad,
            # El enunciado pide indicar "como tomarlo": las indicaciones son obligatorias.
            indicaciones=v.texto(datos.get("indicaciones"), "indicaciones de uso",
                                 minimo=3, maximo=300),
        )
        return self.recetas.guardar(receta)

    def entregar_medicamento(self, receta_id: int):
        """El cargo se genera al entregar, no al recetar: si no se entrega, no se cobra."""
        receta = self.recetas.obtener(receta_id)
        if receta is None:
            raise ErrorNegocio("La receta indicada no existe.")
        if receta.entregado:
            raise ErrorNegocio("Ese medicamento ya fue entregado.")

        receta.entregado = True
        receta.fecha_entrega = datetime.now()
        self.recetas.confirmar()

        cargo, advertencia = self._cobrar(
            receta.visita.paciente, receta.tarifa_id, receta.cantidad, receta.visita_id)
        if cargo:
            receta.cargo_id = cargo["id"]
            self.recetas.confirmar()
        return receta, advertencia

    # ---------- apoyo ----------
    def _cobrar(self, paciente: Paciente, tarifa_id: int, cantidad: int, visita_id: int):
        """
        Delega el cobro en ms-costos. Si el microservicio no responde, el registro
        clinico ya quedo guardado y solo se avisa: el expediente no depende del cobro.
        """
        try:
            cargo = self.costos.registrar_cargo({
                "paciente_id": paciente.id,
                "paciente_nombre": paciente.nombre,
                "tarifa_id": tarifa_id,
                "cantidad": cantidad,
                "visita_id": visita_id,
            })
            return cargo, None
        except MicroservicioError as error:
            return None, (
                "El registro clinico se guardo, pero el cargo no se pudo enviar al "
                f"servicio de costos. {error}")

    def _buscar_tarifa(self, tarifa_id: int, tipo: str | None = None) -> dict:
        try:
            tarifas = self.costos.listar_tarifas()
        except MicroservicioError as error:
            raise ErrorNegocio(f"No se pudo consultar el catalogo de tarifas. {error}")
        tarifa = next((t for t in tarifas if t["id"] == tarifa_id), None)
        if tarifa is None:
            raise ErrorNegocio("La tarifa seleccionada no existe o esta inactiva.")
        if tipo and tarifa["tipo_servicio"] != tipo:
            raise ErrorNegocio("La tarifa seleccionada no corresponde a este tipo de servicio.")
        return tarifa

    def _buscar_solicitud(self, solicitud_id: int) -> Solicitud:
        solicitud = self.solicitudes.obtener(solicitud_id)
        if solicitud is None:
            raise ErrorNegocio("La solicitud indicada no existe.")
        return solicitud

    def _buscar_visita(self, visita_id: int) -> VisitaMedica:
        visita = self.visitas.obtener(visita_id)
        if visita is None:
            raise ErrorNegocio("La visita medica indicada no existe.")
        return visita


# ------------------------------------------------------------- Consultas
class ConsultaService:
    """Lecturas para las pantallas. No modifica nada."""

    def __init__(self, sesion):
        self.pacientes = PacienteRepository(sesion)
        self.solicitudes = SolicitudRepository(sesion)
        self.visitas = VisitaRepository(sesion)
        self.examenes = ExamenRepository(sesion)
        self.recetas = RecetaRepository(sesion)
        self.catalogo = CatalogoRepository(sesion)
        self.costos = ClienteCostos()
        self.notificaciones = ClienteNotificaciones()

    def resumen_panel(self) -> dict:
        return {
            "internos": self.pacientes.contar(),
            "solicitudes_pendientes": self.solicitudes.contar_pendientes(),
            "visitas_abiertas": self.visitas.contar_abiertas(),
            "examenes_pendientes": self.examenes.contar_pendientes(),
            "medicamentos_pendientes": self.recetas.contar_pendientes(),
        }

    def estado_servicios(self) -> dict:
        return {
            "costos": self.costos.disponible(),
            "notificaciones": self.notificaciones.disponible(),
        }

    def tarifas_por_tipo(self, tipo: str | None = None) -> list:
        try:
            tarifas = self.costos.listar_tarifas()
        except MicroservicioError:
            return []
        if tipo:
            return [t for t in tarifas if t["tipo_servicio"] == tipo]
        return tarifas

    def cuenta_del_paciente(self, paciente_id: int):
        try:
            cargos = self.costos.listar_cargos(paciente_id)
            cuenta = self.costos.estado_cuenta(paciente_id)
        except MicroservicioError:
            return [], None
        return cargos, cuenta

    def correos_del_paciente(self, paciente_id: int) -> list:
        try:
            return self.notificaciones.listar(paciente_id)
        except MicroservicioError:
            return []


# ------------------------------------------------------------------- Caja
class CajaService:
    """
    Tesoreria del asilo: donaciones, gastos operativos y cuotas mensuales.

    Estos movimientos son internos del asilo y no pasan por ms-costos, que
    administra unicamente lo que se cobra al familiar por los servicios de la
    fundacion (consultas, examenes y medicamentos).
    """

    def __init__(self, sesion):
        self.donaciones = DonacionRepository(sesion)
        self.gastos = GastoRepository(sesion)
        self.cuotas = CuotaRepository(sesion)
        self.pacientes = PacienteRepository(sesion)
        self.pagos_fundacion = PagoFundacionRepository(sesion)
        self.costos = ClienteCostos()

    # ---------- donaciones ----------
    def registrar_donacion(self, datos: dict, usuario: str = "") -> Donacion:
        donacion = Donacion(
            origen=v.opcion(datos.get("origen"), OrigenDonacion, "origen de la donacion"),
            donante=v.texto(datos.get("donante"), "donante", minimo=3, maximo=150),
            monto=float(v.monto(datos.get("monto"))),
            fecha=v.fecha(datos.get("fecha"), "fecha de la donacion"),
            descripcion=v.texto(datos.get("descripcion"), "descripcion", obligatorio=False,
                                maximo=300),
            recibo=v.texto(datos.get("recibo"), "recibo", obligatorio=False, maximo=40),
            registrada_por=usuario,
        )
        return self.donaciones.guardar(donacion)

    def eliminar_donacion(self, donacion_id: int) -> Donacion:
        donacion = self.donaciones.obtener(donacion_id)
        if donacion is None:
            raise ErrorNegocio("La donacion indicada no existe.")
        self.donaciones.eliminar(donacion)
        return donacion

    # ---------- gastos ----------
    def registrar_gasto(self, datos: dict, usuario: str = "") -> Gasto:
        gasto = Gasto(
            categoria=v.opcion(datos.get("categoria"), CategoriaGasto, "categoria del gasto"),
            descripcion=v.texto(datos.get("descripcion"), "descripcion del gasto", minimo=3,
                                maximo=300),
            monto=float(v.monto(datos.get("monto"))),
            fecha=v.fecha(datos.get("fecha"), "fecha del gasto"),
            comprobante=v.texto(datos.get("comprobante"), "comprobante", obligatorio=False,
                                maximo=40),
            registrado_por=usuario,
        )
        return self.gastos.guardar(gasto)

    def eliminar_gasto(self, gasto_id: int) -> Gasto:
        gasto = self.gastos.obtener(gasto_id)
        if gasto is None:
            raise ErrorNegocio("El gasto indicado no existe.")
        self.gastos.eliminar(gasto)
        return gasto

    # ---------- cuotas mensuales ----------
    def generar_cuotas_del_mes(self, anio: int, mes: int) -> int:
        """
        Crea la cuota de cada interno activo para el mes indicado.
        No duplica: si la cuota ya existe, la deja como esta.
        """
        mes = v.entero(mes, "mes", 1, 12)
        anio = v.entero(anio, "anio", 2000, date.today().year + 1)
        creadas = 0
        for paciente in self.pacientes.listar():
            if paciente.cuota_mensual <= 0:
                continue
            if self.cuotas.existe(paciente.id, anio, mes):
                continue
            self.cuotas.guardar(CuotaMensual(
                paciente_id=paciente.id, anio=anio, mes=mes,
                monto=paciente.cuota_mensual))
            creadas += 1
        return creadas

    def cobrar_cuota(self, cuota_id: int) -> CuotaMensual:
        cuota = self.cuotas.obtener(cuota_id)
        if cuota is None:
            raise ErrorNegocio("La cuota indicada no existe.")
        if cuota.pagada:
            raise ErrorNegocio("Esa cuota ya fue cobrada.")
        cuota.pagada = True
        cuota.fecha_pago = datetime.now()
        self.cuotas.confirmar()
        return cuota

    # ---------- pagos a la fundacion (RF-25) ----------
    def estado_con_fundacion(self) -> dict:
        """
        Deuda del asilo con la fundacion = total facturado por sus servicios
        (cargos de ms-costos, ya con el descuento) menos lo que el asilo le pago.
        No depende de si el familiar ya pago su cargo: son dos cuentas distintas.
        """
        try:
            cargos = self.costos.listar_cargos()
        except MicroservicioError as error:
            raise ErrorNegocio(
                f"No se pudo consultar lo facturado por la fundacion. {error}")
        facturado = sum(Decimal(str(c["total"])) for c in cargos)
        pagado = Decimal(str(self.pagos_fundacion.total()))
        return {"facturado": float(facturado), "pagado": float(pagado),
                "deuda": float(facturado - pagado)}

    def registrar_pago_fundacion(self, datos: dict, usuario: str = "") -> PagoFundacion:
        monto = v.monto(datos.get("monto"), "monto del pago")
        referencia = v.texto(datos.get("referencia"), "referencia o numero de factura",
                             minimo=3, maximo=60)
        if self.pagos_fundacion.existe_referencia(referencia):
            raise ErrorNegocio(
                f"Ya existe un pago con la referencia {referencia}. "
                "Verifique que no se este registrando dos veces.")
        deuda = Decimal(str(self.estado_con_fundacion()["deuda"])).quantize(v.CENTAVO)
        if monto > deuda:
            raise ErrorNegocio(
                f"El pago (Q{monto:,.2f}) es mayor que la deuda actual con la "
                f"fundacion (Q{deuda:,.2f}).")
        pago = PagoFundacion(
            fecha=v.fecha(datos.get("fecha"), "fecha del pago"),
            monto=float(monto),
            referencia=referencia,
            descripcion=v.texto(datos.get("descripcion"), "descripcion", obligatorio=False,
                                maximo=300),
            registrado_por=usuario,
        )
        return self.pagos_fundacion.guardar(pago)


# --------------------------------------------- Cobros al familiar (ms-costos)
class CobroService:
    """
    Acciones de caja sobre los cargos a la cuenta del familiar. Las rutas no
    llaman al microservicio directamente: pasan por esta capa de negocio.
    """

    def __init__(self, sesion=None):
        self.costos = ClienteCostos()

    def pagar_cargo(self, cargo_id: int) -> dict:
        try:
            return self.costos.pagar_cargo(cargo_id)
        except MicroservicioError as error:
            raise ErrorNegocio(f"No se pudo registrar el pago. {error}")

    def revertir_pago(self, cargo_id: int, motivo: str) -> dict:
        """Corrige un pago registrado por error (DEF-05). Exige el motivo."""
        motivo = v.texto(motivo, "motivo de la reversion", minimo=5, maximo=200)
        try:
            return self.costos.revertir_pago(cargo_id, motivo)
        except MicroservicioError as error:
            raise ErrorNegocio(f"No se pudo revertir el pago. {error}")

    def eliminar_cargo(self, cargo_id: int) -> None:
        try:
            self.costos.eliminar_cargo(cargo_id)
        except MicroservicioError as error:
            raise ErrorNegocio(f"No se pudo eliminar el cargo. {error}")
