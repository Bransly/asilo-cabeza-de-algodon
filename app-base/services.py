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
"""
from datetime import date, datetime

from clientes import ClienteCostos, ClienteNotificaciones, MicroservicioError
from models import (
    CategoriaGasto, CuotaMensual, Donacion, EstadoExamen, EstadoSolicitud,
    EstadoVisita, FichaMedica, Gasto, Medico, MedicamentoPermanente,
    MedicamentoRecetado, OrdenExamen, OrigenDonacion, Paciente, Solicitud,
    VisitaMedica,
)
from repository import (
    CatalogoRepository, CuotaRepository, DonacionRepository, ExamenRepository,
    FichaRepository, GastoRepository, MedicamentoPermanenteRepository,
    PacienteRepository, RecetaRepository, SolicitudRepository, VisitaRepository,
    marcar_actualizada,
)


class ErrorNegocio(Exception):
    """Regla del asilo incumplida. Se muestra al usuario como aviso."""


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

    def registrar(self, datos: dict) -> Paciente:
        if not datos.get("nombre") or not datos.get("familiar_nombre"):
            raise ErrorNegocio("El nombre del interno y el del familiar son obligatorios.")
        if not datos.get("correo_familiar"):
            raise ErrorNegocio(
                "El correo del familiar es obligatorio: el sistema debe notificarle "
                "cada solicitud medica.")

        paciente = Paciente(
            nombre=datos["nombre"].strip(),
            edad=int(datos.get("edad") or 0),
            motivo_ingreso=datos.get("motivo_ingreso", "").strip(),
            familiar_nombre=datos["familiar_nombre"].strip(),
            correo_familiar=datos["correo_familiar"].strip(),
            telefono_familiar=datos.get("telefono_familiar", "").strip(),
            cuota_mensual=float(datos.get("cuota_mensual") or 0),
        )
        if datos.get("fecha_ingreso"):
            paciente.fecha_ingreso = datetime.strptime(
                datos["fecha_ingreso"], "%Y-%m-%d").date()

        # Todo interno nace con su ficha medica: sin ficha no puede ser atendido.
        paciente.ficha = FichaMedica(
            psicopatologia=datos.get("psicopatologia", "").strip(),
            padecimientos=datos.get("padecimientos", "").strip(),
        )
        return self.pacientes.guardar(paciente)

    def actualizar(self, paciente_id: int, datos: dict) -> Paciente:
        paciente = self.obtener(paciente_id)
        paciente.nombre = datos.get("nombre", paciente.nombre).strip()
        paciente.edad = int(datos.get("edad") or paciente.edad)
        paciente.motivo_ingreso = datos.get("motivo_ingreso", paciente.motivo_ingreso)
        paciente.familiar_nombre = datos.get("familiar_nombre", paciente.familiar_nombre)
        paciente.correo_familiar = datos.get("correo_familiar", paciente.correo_familiar)
        paciente.telefono_familiar = datos.get("telefono_familiar", paciente.telefono_familiar)
        paciente.cuota_mensual = float(datos.get("cuota_mensual") or paciente.cuota_mensual)
        self.pacientes.confirmar()
        return paciente

    def dar_de_baja(self, paciente_id: int) -> Paciente:
        paciente = self.obtener(paciente_id)
        self.pacientes.eliminar(paciente)
        return paciente

    def actualizar_ficha(self, paciente_id: int, datos: dict) -> FichaMedica:
        paciente = self.obtener(paciente_id)
        ficha = paciente.ficha or FichaMedica(paciente_id=paciente.id)
        ficha.psicopatologia = datos.get("psicopatologia", "").strip()
        ficha.padecimientos = datos.get("padecimientos", "").strip()
        ficha.alergias = datos.get("alergias", "").strip()
        ficha.observaciones = datos.get("observaciones", "").strip()
        marcar_actualizada(ficha)
        return self.fichas.guardar(ficha)

    def agregar_medicamento_permanente(self, paciente_id: int, datos: dict):
        paciente = self.obtener(paciente_id)
        if not datos.get("nombre"):
            raise ErrorNegocio("Indique el nombre del medicamento.")
        medicamento = MedicamentoPermanente(
            paciente_id=paciente.id,
            nombre=datos["nombre"].strip(),
            dosis=datos.get("dosis", "").strip(),
            frecuencia=datos.get("frecuencia", "").strip(),
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
        paciente = self.pacientes.obtener(int(datos["paciente_id"]))
        if paciente is None:
            raise ErrorNegocio("El interno indicado no existe.")
        if paciente.ficha is None:
            raise ErrorNegocio(
                "El interno no tiene ficha medica. Complete la ficha antes de referirlo.")
        if not datos.get("motivo", "").strip():
            raise ErrorNegocio("Escriba el motivo de la referencia.")

        solicitud = Solicitud(
            paciente_id=paciente.id,
            especialidad_id=int(datos["especialidad_id"]),
            enfermero_id=int(datos["enfermero_id"]) if datos.get("enfermero_id") else None,
            motivo=datos["motivo"].strip(),
            estado_paciente=datos.get("estado_paciente", "Estable").strip() or "Estable",
        )
        self.solicitudes.guardar(solicitud)
        solicitud = self.solicitudes.obtener(solicitud.id)

        advertencia = self._avisar_al_familiar(solicitud)
        return solicitud, advertencia

    def _avisar_al_familiar(self, solicitud: Solicitud) -> str | None:
        """
        Requisito adicional del enunciado: avisar por correo al familiar cuando se
        crea una solicitud. Si el microservicio falla, la solicitud NO se pierde;
        por eso el correo esta separado del registro clinico.
        """
        try:
            self.notificaciones.notificar_solicitud({
                "paciente_id": solicitud.paciente.id,
                "paciente_nombre": solicitud.paciente.nombre,
                "familiar_nombre": solicitud.paciente.familiar_nombre,
                "correo_destino": solicitud.paciente.correo_familiar,
                "especialidad": solicitud.especialidad.nombre,
                "medico_asignado": (
                    solicitud.medico.nombre if solicitud.medico else "Medico por asignar"),
                "motivo": solicitud.motivo,
                "estado_paciente": solicitud.estado_paciente,
            })
            return None
        except MicroservicioError as error:
            return f"La solicitud se registro, pero no se pudo avisar al familiar. {error}"

    # ---------- 2. La fundacion asigna medico y horario ----------
    def asignar_solicitud(self, solicitud_id: int, datos: dict) -> Solicitud:
        solicitud = self._buscar_solicitud(solicitud_id)
        if solicitud.estado == EstadoSolicitud.ATENDIDA:
            raise ErrorNegocio("Esa solicitud ya fue atendida y no puede reasignarse.")

        medico = self.sesion.get(Medico, int(datos["medico_id"]))
        if medico is None:
            raise ErrorNegocio("El medico indicado no existe.")
        if medico.especialidad_id != solicitud.especialidad_id:
            raise ErrorNegocio(
                f"{medico.nombre} no pertenece a la especialidad solicitada "
                f"({solicitud.especialidad.nombre}).")

        # Se asigna el objeto, no solo el id, para que la relacion quede cargada
        # y la vista pueda mostrar el nombre del medico sin volver a consultar.
        solicitud.medico = medico
        solicitud.fecha_asignada = datetime.strptime(datos["fecha_asignada"], "%Y-%m-%dT%H:%M")
        solicitud.estado = EstadoSolicitud.ASIGNADA
        self.solicitudes.confirmar()
        return solicitud

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
        visita.diagnostico = datos.get("diagnostico", "").strip()
        visita.observaciones = datos.get("observaciones", "").strip()
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

        tarifa = self._buscar_tarifa(int(datos["tarifa_id"]))
        examen = OrdenExamen(
            visita_id=visita.id,
            tarifa_id=tarifa["id"],
            nombre=tarifa["descripcion"],
            indicaciones=datos.get("indicaciones", "").strip(),
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
        if not resultado.strip():
            raise ErrorNegocio("Escriba el resultado del examen.")
        examen.resultado = resultado.strip()
        examen.estado = EstadoExamen.CON_RESULTADO
        examen.fecha_resultado = datetime.now()
        self.examenes.confirmar()
        return examen

    # ---------- 5. Farmacia ----------
    def recetar_medicamento(self, visita_id: int, datos: dict) -> MedicamentoRecetado:
        visita = self._buscar_visita(visita_id)
        if visita.estado == EstadoVisita.CERRADA:
            raise ErrorNegocio("La visita esta cerrada: no admite recetas nuevas.")

        tarifa = self._buscar_tarifa(int(datos["tarifa_id"]))
        cantidad = int(datos.get("cantidad") or 1)
        if cantidad < 1:
            raise ErrorNegocio("La cantidad debe ser mayor que cero.")

        receta = MedicamentoRecetado(
            visita_id=visita.id,
            tarifa_id=tarifa["id"],
            nombre=tarifa["descripcion"],
            cantidad=cantidad,
            indicaciones=datos.get("indicaciones", "").strip(),
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

    def _buscar_tarifa(self, tarifa_id: int) -> dict:
        try:
            tarifas = self.costos.listar_tarifas()
        except MicroservicioError as error:
            raise ErrorNegocio(f"No se pudo consultar el catalogo de tarifas. {error}")
        tarifa = next((t for t in tarifas if t["id"] == tarifa_id), None)
        if tarifa is None:
            raise ErrorNegocio("La tarifa seleccionada no existe o esta inactiva.")
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

    # ---------- donaciones ----------
    def registrar_donacion(self, datos: dict, usuario: str = "") -> Donacion:
        monto = self._monto(datos.get("monto"))
        if not datos.get("donante", "").strip():
            raise ErrorNegocio("Indique quien realiza la donacion.")
        donacion = Donacion(
            origen=OrigenDonacion(datos["origen"]),
            donante=datos["donante"].strip(),
            monto=monto,
            fecha=self._fecha(datos.get("fecha")),
            descripcion=datos.get("descripcion", "").strip(),
            recibo=datos.get("recibo", "").strip(),
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
        monto = self._monto(datos.get("monto"))
        if not datos.get("descripcion", "").strip():
            raise ErrorNegocio("Describa el gasto realizado.")
        gasto = Gasto(
            categoria=CategoriaGasto(datos["categoria"]),
            descripcion=datos["descripcion"].strip(),
            monto=monto,
            fecha=self._fecha(datos.get("fecha")),
            comprobante=datos.get("comprobante", "").strip(),
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
        if not 1 <= mes <= 12:
            raise ErrorNegocio("El mes debe estar entre 1 y 12.")
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

    # ---------- apoyo ----------
    @staticmethod
    def _monto(valor) -> float:
        try:
            monto = float(valor)
        except (TypeError, ValueError):
            raise ErrorNegocio("El monto debe ser un numero.")
        if monto <= 0:
            raise ErrorNegocio("El monto debe ser mayor que cero.")
        return monto

    @staticmethod
    def _fecha(texto):
        if not texto:
            return date.today()
        try:
            return datetime.strptime(texto, "%Y-%m-%d").date()
        except ValueError:
            raise ErrorNegocio("La fecha no tiene un formato valido.")
