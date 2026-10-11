"""
APLICACION BASE - Panel del Asilo Cabeza de Algodon

Monolito del sistema: aqui vive el expediente clinico (pacientes, ficha medica,
solicitudes, visitas, examenes y recetas). Los costos y los correos NO estan
aqui: se delegan en los microservicios ms-costos y ms-notificaciones.

Este archivo es solo la capa de presentacion: recibe HTTP, llama a la capa de
negocio y devuelve una plantilla. No contiene reglas de negocio ni SQL.
"""
import os
from datetime import date, datetime, timedelta

from flask import Flask, flash, redirect, render_template, request, session, url_for

from auth import (
    AutenticacionService, ErrorAutenticacion, UsuarioService, requiere_rol, usuario_actual,
)
from database import Sesion, crear_tablas
from models import (
    ETIQUETA_GASTO, ETIQUETA_ORIGEN, ETIQUETA_ROL, CategoriaGasto,
    EstadoSolicitud, OrigenDonacion, RolUsuario,
)
from reportes import MESES, ReporteService
from semilla import cargar_datos_iniciales
from services import (
    AtencionService, CajaService, CobroService, ConsultaService, ErrorNegocio,
    PacienteService,
)

app = Flask(__name__)

# La llave que firma la cookie de sesion NO tiene valor por defecto: si faltara,
# cualquiera que leyera el codigo podria falsificar sesiones. Se define en el
# archivo .env (fuera del repositorio) o en las variables del servidor.
app.secret_key = os.getenv("SECRET_KEY", "")
if len(app.secret_key) < 32:
    raise RuntimeError(
        "Defina SECRET_KEY (mínimo 32 caracteres) en el archivo .env. "
        "Puede generarla con: python -c \"import secrets; print(secrets.token_hex(32))\"")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # JavaScript no puede leer la cookie
    SESSION_COOKIE_SAMESITE="Lax",    # mitiga CSRF entre sitios
    SESSION_COOKIE_SECURE=os.getenv("HTTPS", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=1024 * 1024,   # ningun formulario necesita mas de 1 MB
)

# Fuentes externas permitidas por la politica de contenido (CSP).
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
])

R = RolUsuario

# Quien abre expedientes. Laboratorio, farmacia y fundacion trabajan desde sus
# bandejas y la visita; no ven el expediente completo ni la cuenta del familiar.
ROLES_EXPEDIENTE = (R.MEDICO_GENERAL, R.MEDICO_ESPECIALISTA, R.ENFERMERIA, R.CAJA)
# Quien ve el estado de cuenta del familiar (informacion financiera, RN-10).
ROLES_CUENTA = ("ADMINISTRADOR", "CAJA")


@app.before_request
def abrir_sesion():
    request.sesion = Sesion()


@app.after_request
def encabezados_de_seguridad(respuesta):
    """Encabezados HTTP de seguridad (hallazgo H-09 del SQA)."""
    respuesta.headers["Content-Security-Policy"] = CSP
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    respuesta.headers["X-Frame-Options"] = "DENY"
    respuesta.headers["Referrer-Policy"] = "same-origin"
    respuesta.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if app.config["SESSION_COOKIE_SECURE"]:
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
    # Las pantallas con datos clinicos no se guardan en la cache del navegador.
    if request.endpoint != "static":
        respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@app.errorhandler(413)
def demasiado_grande(_error):
    flash("La información enviada excede el tamaño permitido.", "danger")
    return redirect(request.referrer or url_for("panel"))


@app.teardown_request
def cerrar_sesion(excepcion=None):
    sesion = getattr(request, "sesion", None)
    if sesion is not None:
        sesion.close()


def volver(destino, **valores):
    return redirect(url_for(destino, **valores))


@app.context_processor
def datos_de_sesion():
    """Deja el usuario autenticado disponible en todas las plantillas."""
    rol = session.get("rol")
    return {"usuario": usuario_actual(), "etiquetas_rol": ETIQUETA_ROL,
            "puede_ver_expediente": rol == "ADMINISTRADOR"
            or rol in [r.value for r in ROLES_EXPEDIENTE]}


# ================================================================ Seguridad
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if usuario_actual():
            return volver("panel")
        return render_template("login.html", siguiente=request.args.get("siguiente", ""))

    autenticacion = AutenticacionService(request.sesion)
    try:
        usuario = autenticacion.iniciar_sesion(
            request.form.get("usuario", ""), request.form.get("contrasena", ""))
        flash(f"Bienvenido(a), {usuario.nombre}.", "success")
        siguiente = request.form.get("siguiente", "")
        # Solo se acepta una ruta interna: evita redireccion abierta a otro sitio.
        if siguiente.startswith("/") and not siguiente.startswith("//"):
            return redirect(siguiente)
        return volver("panel")
    except ErrorAutenticacion as error:
        flash(str(error), "danger")
        return volver("login")


@app.post("/logout")
def logout():
    AutenticacionService(request.sesion).cerrar_sesion()
    flash("Sesión cerrada.", "success")
    return volver("login")


@app.route("/cuenta/contrasena", methods=["GET", "POST"])
@requiere_rol()
def cambiar_contrasena():
    """Cambio de contrasena; obligatorio en el primer ingreso."""
    if request.method == "GET":
        return render_template("contrasena.html", obligatorio=session.get("debe_cambiar"))
    try:
        AutenticacionService(request.sesion).cambiar_contrasena(
            request.form.get("actual", ""), request.form.get("nueva", ""),
            request.form.get("confirmacion", ""))
        flash("Contraseña actualizada.", "success")
        return volver("panel")
    except ErrorAutenticacion as error:
        flash(str(error), "danger")
        return volver("cambiar_contrasena")


@app.route("/bitacora")
@requiere_rol(R.ADMINISTRADOR)
def bitacora():
    """Auditoria: quien hizo que, cuando y con que resultado."""
    from repository import BitacoraRepository
    consultas = ConsultaService(request.sesion)
    return render_template(
        "bitacora.html",
        registros=BitacoraRepository(request.sesion).ultimos(150),
        estado_servicios=consultas.estado_servicios(),
    )


@app.route("/usuarios")
@requiere_rol(R.ADMINISTRADOR)
def usuarios():
    """Administracion de cuentas: desbloquear, restablecer contrasena, activar."""
    return render_template(
        "usuarios.html", usuarios_sistema=UsuarioService(request.sesion).listar(),
        ahora=datetime.now(), estado_servicios=ConsultaService(request.sesion).estado_servicios())


@app.post("/usuarios/<int:usuario_id>/<accion>")
@requiere_rol(R.ADMINISTRADOR)
def administrar_usuario(usuario_id: int, accion: str):
    servicio = UsuarioService(request.sesion)
    auditoria = AutenticacionService(request.sesion)
    try:
        if accion == "restablecer":
            usuario, temporal = servicio.restablecer_contrasena(usuario_id)
            auditoria.registrar("RESTABLECE_CONTRASENA", "Usuario", usuario_id, "EXITO",
                                usuario.usuario)
            # La clave temporal se muestra una sola vez y no queda en la bitacora.
            flash(f"Clave temporal de {usuario.usuario}: {temporal} . Entréguela en persona; "
                  "el sistema le pedirá cambiarla al ingresar.", "warning")
        elif accion == "desbloquear":
            usuario = servicio.desbloquear(usuario_id)
            auditoria.registrar("DESBLOQUEA_USUARIO", "Usuario", usuario_id, "EXITO", usuario.usuario)
            flash(f"Cuenta {usuario.usuario} desbloqueada.", "success")
        elif accion in ("activar", "desactivar"):
            usuario = servicio.cambiar_estado(usuario_id, accion == "activar")
            auditoria.registrar(accion.upper() + "_USUARIO", "Usuario", usuario_id, "EXITO",
                                usuario.usuario)
            flash(f"Cuenta {usuario.usuario} {'activada' if usuario.activo else 'desactivada'}.",
                  "success")
        else:
            flash("Acción no válida.", "danger")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("usuarios")


# ============================================================ Panel general
@app.route("/")
@requiere_rol()
def panel():
    consultas = ConsultaService(request.sesion)
    return render_template(
        "panel.html",
        resumen=consultas.resumen_panel(),
        estado_servicios=consultas.estado_servicios(),
        solicitudes=consultas.solicitudes.listar()[:6],
    )


# =============================================================== Pacientes
@app.route("/pacientes")
@requiere_rol(*ROLES_EXPEDIENTE)
def pacientes():
    servicio = PacienteService(request.sesion)
    consultas = ConsultaService(request.sesion)
    return render_template(
        "pacientes.html",
        pacientes=servicio.listar(),
        hoy=date.today().isoformat(),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/pacientes")
@requiere_rol(R.ADMINISTRADOR)
def crear_paciente():
    servicio = PacienteService(request.sesion)
    try:
        paciente = servicio.registrar(request.form.to_dict())
        AutenticacionService(request.sesion).registrar(
            "ALTA_INTERNO", "Paciente", paciente.id, "EXITO", paciente.nombre)
        flash(f"Interno registrado: {paciente.nombre}.", "success")
        return volver("expediente", paciente_id=paciente.id)
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("pacientes")


@app.route("/pacientes/<int:paciente_id>")
@requiere_rol(*ROLES_EXPEDIENTE)
def expediente(paciente_id: int):
    servicio = PacienteService(request.sesion)
    consultas = ConsultaService(request.sesion)
    atencion = AtencionService(request.sesion)

    try:
        paciente = servicio.obtener(paciente_id)
    except ErrorNegocio as error:
        flash(str(error), "danger")
        return volver("pacientes")

    # La cuenta del familiar solo se consulta para los roles que pueden verla.
    cargos, cuenta = ([], None)
    if session.get("rol") in ROLES_CUENTA:
        cargos, cuenta = consultas.cuenta_del_paciente(paciente_id)

    return render_template(
        "expediente.html",
        paciente=paciente,
        historial=atencion.visitas.historial(paciente_id),
        especialidades=consultas.catalogo.especialidades(),
        enfermeros=consultas.catalogo.enfermeros(),
        cargos=cargos,
        cuenta=cuenta,
        puede_ver_cuenta=session.get("rol") in ROLES_CUENTA,
        correos=consultas.correos_del_paciente(paciente_id),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/pacientes/<int:paciente_id>/editar")
@requiere_rol(R.ADMINISTRADOR)
def editar_paciente(paciente_id: int):
    servicio = PacienteService(request.sesion)
    try:
        servicio.actualizar(paciente_id, request.form.to_dict())
        flash("Datos del interno actualizados.", "success")
    except (ErrorNegocio, ValueError) as error:
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.post("/pacientes/<int:paciente_id>/baja")
@requiere_rol(R.ADMINISTRADOR)
def dar_de_baja(paciente_id: int):
    servicio = PacienteService(request.sesion)
    try:
        paciente = servicio.dar_de_baja(paciente_id)
        AutenticacionService(request.sesion).registrar(
            "BAJA_INTERNO", "Paciente", paciente_id, "EXITO", paciente.nombre)
        flash(f"{paciente.nombre} fue dado de baja. Su expediente se conserva.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("pacientes")


@app.post("/pacientes/<int:paciente_id>/ficha")
@requiere_rol(R.MEDICO_GENERAL, R.MEDICO_ESPECIALISTA)
def guardar_ficha(paciente_id: int):
    servicio = PacienteService(request.sesion)
    try:
        servicio.actualizar_ficha(paciente_id, request.form.to_dict())
        AutenticacionService(request.sesion).registrar(
            "EDITA_FICHA", "FichaMedica", paciente_id, "EXITO")
        flash("Ficha médica actualizada.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.post("/pacientes/<int:paciente_id>/medicamentos")
@requiere_rol(R.MEDICO_GENERAL, R.ENFERMERIA)
def agregar_medicamento(paciente_id: int):
    servicio = PacienteService(request.sesion)
    try:
        servicio.agregar_medicamento_permanente(paciente_id, request.form.to_dict())
        flash("Medicamento permanente agregado.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.post("/medicamentos/<int:medicamento_id>/eliminar")
@requiere_rol(R.MEDICO_GENERAL, R.ENFERMERIA)
def eliminar_medicamento(medicamento_id: int):
    servicio = PacienteService(request.sesion)
    paciente_id = request.form.get("paciente_id", type=int)
    try:
        servicio.quitar_medicamento_permanente(medicamento_id)
        flash("Medicamento permanente eliminado.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


# ============================================================= Solicitudes
@app.post("/solicitudes")
@requiere_rol(R.MEDICO_GENERAL)
def crear_solicitud():
    atencion = AtencionService(request.sesion)
    paciente_id = request.form.get("paciente_id", type=int)
    try:
        solicitud, advertencia = atencion.crear_solicitud(request.form.to_dict())
        flash(
            f"Solicitud #{solicitud.id} enviada a la fundación "
            f"({solicitud.especialidad.nombre}). Se notificó a "
            f"{solicitud.paciente.familiar_nombre}.", "success")
        if advertencia:
            flash(advertencia, "warning")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.route("/fundacion")
@requiere_rol(R.FUNDACION, R.MEDICO_ESPECIALISTA)
def fundacion():
    """Modulo que se le proporciona a la fundacion para asignar medico y horario."""
    consultas = ConsultaService(request.sesion)
    filtro = request.args.get("estado", "PENDIENTE")
    estado = EstadoSolicitud(filtro) if filtro in EstadoSolicitud.__members__ else None

    return render_template(
        "fundacion.html",
        solicitudes=consultas.solicitudes.listar(estado),
        medicos=consultas.catalogo.medicos(),
        tarifas_consulta=consultas.tarifas_por_tipo("CONSULTA"),
        filtro=filtro,
        ahora=datetime.now().strftime("%Y-%m-%dT%H:%M"),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/solicitudes/<int:solicitud_id>/asignar")
@requiere_rol(R.FUNDACION)
def asignar_solicitud(solicitud_id: int):
    atencion = AtencionService(request.sesion)
    try:
        solicitud, advertencia = atencion.asignar_solicitud(
            solicitud_id, request.form.to_dict())
        flash(
            f"Solicitud #{solicitud.id} asignada a {solicitud.medico.nombre} "
            f"para el {solicitud.fecha_asignada.strftime('%d/%m/%Y %H:%M')}. "
            "Se aviso al familiar.", "success")
        if advertencia:
            flash(advertencia, "warning")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("fundacion", estado=request.form.get("filtro", "PENDIENTE"))


@app.post("/solicitudes/<int:solicitud_id>/visita")
@requiere_rol(R.FUNDACION, R.MEDICO_ESPECIALISTA)
def abrir_visita(solicitud_id: int):
    atencion = AtencionService(request.sesion)
    try:
        visita_medica, advertencia = atencion.convertir_en_visita(
            solicitud_id, request.form.get("tarifa_consulta_id", type=int))
        flash(f"Visita médica #{visita_medica.id} abierta.", "success")
        if advertencia:
            flash(advertencia, "warning")
        return volver("visita", visita_id=visita_medica.id)
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("fundacion")


# ========================================================== Visita medica
@app.route("/visitas/<int:visita_id>")
@requiere_rol()
def visita(visita_id: int):
    atencion = AtencionService(request.sesion)
    consultas = ConsultaService(request.sesion)
    visita_medica = atencion.visitas.obtener(visita_id)
    if visita_medica is None:
        flash("La visita médica indicada no existe.", "danger")
        return volver("panel")

    return render_template(
        "visita.html",
        visita=visita_medica,
        tarifas_examen=consultas.tarifas_por_tipo("EXAMEN"),
        tarifas_medicamento=consultas.tarifas_por_tipo("MEDICAMENTO"),
        historial=atencion.visitas.historial(visita_medica.paciente_id),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/visitas/<int:visita_id>/diagnostico")
@requiere_rol(R.MEDICO_ESPECIALISTA)
def guardar_diagnostico(visita_id: int):
    atencion = AtencionService(request.sesion)
    try:
        atencion.registrar_diagnostico(visita_id, request.form.to_dict())
        flash("Diagnóstico y observaciones guardados.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("visita", visita_id=visita_id)


@app.post("/visitas/<int:visita_id>/cerrar")
@requiere_rol(R.MEDICO_ESPECIALISTA)
def cerrar_visita(visita_id: int):
    atencion = AtencionService(request.sesion)
    try:
        atencion.cerrar_visita(visita_id)
        flash("Visita médica cerrada.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("visita", visita_id=visita_id)


@app.post("/visitas/<int:visita_id>/examenes")
@requiere_rol(R.MEDICO_ESPECIALISTA)
def ordenar_examen(visita_id: int):
    atencion = AtencionService(request.sesion)
    try:
        examen, advertencia = atencion.ordenar_examen(visita_id, request.form.to_dict())
        flash(f"Examen solicitado: {examen.nombre}. Se cargo a la cuenta del familiar.",
              "success")
        if advertencia:
            flash(advertencia, "warning")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("visita", visita_id=visita_id)


@app.post("/visitas/<int:visita_id>/recetas")
@requiere_rol(R.MEDICO_ESPECIALISTA)
def recetar(visita_id: int):
    atencion = AtencionService(request.sesion)
    try:
        receta = atencion.recetar_medicamento(visita_id, request.form.to_dict())
        flash(f"Medicamento indicado: {receta.nombre}. Pendiente de entrega en farmacia.",
              "success")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("visita", visita_id=visita_id)


# ============================================================ Laboratorio
@app.route("/laboratorio")
@requiere_rol(R.LABORATORIO)
def laboratorio():
    consultas = ConsultaService(request.sesion)
    return render_template(
        "laboratorio.html",
        pendientes=consultas.examenes.pendientes_de_resultado(),
        recientes=consultas.examenes.con_resultado(),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/examenes/<int:examen_id>/resultado")
@requiere_rol(R.LABORATORIO)
def cargar_resultado(examen_id: int):
    atencion = AtencionService(request.sesion)
    try:
        examen = atencion.cargar_resultado(examen_id, request.form.get("resultado", ""))
        flash(f"Resultado cargado: {examen.nombre}. El médico ya puede consultarlo.",
              "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("laboratorio")


# ================================================================ Farmacia
@app.route("/farmacia")
@requiere_rol(R.FARMACIA)
def farmacia():
    consultas = ConsultaService(request.sesion)
    return render_template(
        "farmacia.html",
        pendientes=consultas.recetas.pendientes_de_entrega(),
        recientes=consultas.recetas.entregadas(),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/recetas/<int:receta_id>/entregar")
@requiere_rol(R.FARMACIA)
def entregar_medicamento(receta_id: int):
    atencion = AtencionService(request.sesion)
    try:
        receta, advertencia = atencion.entregar_medicamento(receta_id)
        flash(f"Medicamento entregado: {receta.nombre} (cantidad {receta.cantidad}). "
              "Se cargo a la cuenta del familiar.", "success")
        if advertencia:
            flash(advertencia, "warning")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("farmacia")


# ==================================================================== Caja
@app.post("/cargos/<int:cargo_id>/pagar")
@requiere_rol(R.CAJA)
def pagar_cargo(cargo_id: int):
    paciente_id = request.form.get("paciente_id", type=int)
    auditoria = AutenticacionService(request.sesion)
    try:
        cargo = CobroService().pagar_cargo(cargo_id)
        auditoria.registrar("PAGO_CARGO", "Cargo", cargo_id, "EXITO",
                            f"Q{cargo['total']:.2f}")
        flash("Cargo marcado como pagado.", "success")
    except ErrorNegocio as error:
        auditoria.registrar("PAGO_CARGO", "Cargo", cargo_id, "FALLIDO", str(error))
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.post("/cargos/<int:cargo_id>/revertir")
@requiere_rol(R.CAJA)
def revertir_pago(cargo_id: int):
    """Corrige un pago marcado por error. Queda en la bitacora con su motivo."""
    paciente_id = request.form.get("paciente_id", type=int)
    motivo = request.form.get("motivo", "")
    auditoria = AutenticacionService(request.sesion)
    try:
        cargo = CobroService().revertir_pago(cargo_id, motivo)
        auditoria.registrar("REVIERTE_PAGO", "Cargo", cargo_id, "EXITO",
                            f"Q{cargo['total']:.2f}. Motivo: {motivo.strip()}")
        flash("El pago se revirtió. El cargo vuelve a estar pendiente.", "success")
    except ErrorNegocio as error:
        auditoria.registrar("REVIERTE_PAGO", "Cargo", cargo_id, "FALLIDO", str(error))
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


@app.post("/cargos/<int:cargo_id>/eliminar")
@requiere_rol(R.CAJA)
def eliminar_cargo(cargo_id: int):
    paciente_id = request.form.get("paciente_id", type=int)
    auditoria = AutenticacionService(request.sesion)
    try:
        CobroService().eliminar_cargo(cargo_id)
        auditoria.registrar("ELIMINA_CARGO", "Cargo", cargo_id, "EXITO")
        flash("Cargo eliminado.", "success")
    except ErrorNegocio as error:
        auditoria.registrar("ELIMINA_CARGO", "Cargo", cargo_id, "FALLIDO", str(error))
        flash(str(error), "danger")
    return volver("expediente", paciente_id=paciente_id)


# ==================================================================== Caja
def _fecha(texto):
    """Convierte el texto de un filtro de fecha; devuelve None si viene vacio."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


@app.route("/caja")
@requiere_rol(R.CAJA)
def caja():
    servicio = CajaService(request.sesion)
    consultas = ConsultaService(request.sesion)
    hoy = date.today()
    anio = request.args.get("anio", type=int) or hoy.year
    mes = request.args.get("mes", type=int) or hoy.month

    donaciones = servicio.donaciones.listar()
    gastos = servicio.gastos.listar()
    cuotas = servicio.cuotas.listar(anio=anio, mes=mes)
    try:
        fundacion = servicio.estado_con_fundacion()
    except ErrorNegocio:
        fundacion = None   # ms-costos fuera de linea: la pantalla lo indica

    return render_template(
        "caja.html",
        donaciones=donaciones, gastos=gastos, cuotas=cuotas,
        anio=anio, mes=mes, meses=MESES,
        origenes=[(o.value, ETIQUETA_ORIGEN[o]) for o in OrigenDonacion],
        categorias=[(c.value, ETIQUETA_GASTO[c]) for c in CategoriaGasto],
        etiqueta_origen=ETIQUETA_ORIGEN, etiqueta_gasto=ETIQUETA_GASTO,
        total_donaciones=servicio.donaciones.total(),
        total_gastos=servicio.gastos.total(),
        total_cuotas=servicio.cuotas.total_cobrado(anio, mes),
        pendiente_cuotas=servicio.cuotas.total_pendiente(anio, mes),
        pagos_fundacion=servicio.pagos_fundacion.listar(),
        fundacion=fundacion,
        pestana=request.args.get("pestana", "cuotas"),
        hoy=hoy.isoformat(),
        estado_servicios=consultas.estado_servicios(),
    )


@app.post("/caja/donaciones")
@requiere_rol(R.CAJA)
def registrar_donacion():
    servicio = CajaService(request.sesion)
    try:
        donacion = servicio.registrar_donacion(
            request.form.to_dict(), session.get("usuario_nombre", ""))
        AutenticacionService(request.sesion).registrar(
            "REGISTRA_DONACION", "Donación", donacion.id, "EXITO",
            f"{donacion.donante} Q{donacion.monto:.2f}")
        flash(f"Donación registrada: {donacion.donante}, Q{donacion.monto:,.2f}.", "success")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("caja")


@app.post("/donaciones/<int:donacion_id>/eliminar")
@requiere_rol(R.CAJA)
def eliminar_donacion(donacion_id: int):
    servicio = CajaService(request.sesion)
    try:
        donacion = servicio.eliminar_donacion(donacion_id)
        AutenticacionService(request.sesion).registrar(
            "ELIMINA_DONACION", "Donación", donacion_id, "EXITO", donacion.donante)
        flash("Donación eliminada.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("caja")


@app.post("/caja/gastos")
@requiere_rol(R.CAJA)
def registrar_gasto():
    servicio = CajaService(request.sesion)
    try:
        gasto = servicio.registrar_gasto(
            request.form.to_dict(), session.get("usuario_nombre", ""))
        AutenticacionService(request.sesion).registrar(
            "REGISTRA_GASTO", "Gasto", gasto.id, "EXITO",
            f"{gasto.descripcion} Q{gasto.monto:.2f}")
        flash(f"Gasto registrado: {gasto.descripcion}, Q{gasto.monto:,.2f}.", "success")
    except (ErrorNegocio, ValueError, KeyError) as error:
        flash(str(error), "danger")
    return volver("caja")


@app.post("/gastos/<int:gasto_id>/eliminar")
@requiere_rol(R.CAJA)
def eliminar_gasto(gasto_id: int):
    servicio = CajaService(request.sesion)
    try:
        servicio.eliminar_gasto(gasto_id)
        AutenticacionService(request.sesion).registrar(
            "ELIMINA_GASTO", "Gasto", gasto_id, "EXITO")
        flash("Gasto eliminado.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("caja")


@app.post("/caja/pagos-fundacion")
@requiere_rol(R.CAJA)
def registrar_pago_fundacion():
    servicio = CajaService(request.sesion)
    try:
        pago = servicio.registrar_pago_fundacion(
            request.form.to_dict(), session.get("usuario_nombre", ""))
        AutenticacionService(request.sesion).registrar(
            "PAGO_FUNDACION", "PagoFundacion", pago.id, "EXITO",
            f"{pago.referencia} Q{pago.monto:.2f}")
        flash(f"Pago a la fundación registrado: Q{pago.monto:,.2f} ({pago.referencia}).",
              "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("caja", pestana="fundacion")


@app.post("/caja/cuotas")
@requiere_rol(R.CAJA)
def generar_cuotas():
    servicio = CajaService(request.sesion)
    anio = request.form.get("anio", type=int)
    mes = request.form.get("mes", type=int)
    try:
        creadas = servicio.generar_cuotas_del_mes(anio, mes)
        if creadas:
            flash(f"Se generaron {creadas} cuotas para {MESES[mes]} de {anio}.", "success")
        else:
            flash("Las cuotas de ese mes ya estaban generadas.", "warning")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("caja", anio=anio, mes=mes)


@app.post("/cuotas/<int:cuota_id>/cobrar")
@requiere_rol(R.CAJA)
def cobrar_cuota(cuota_id: int):
    servicio = CajaService(request.sesion)
    try:
        cuota = servicio.cobrar_cuota(cuota_id)
        AutenticacionService(request.sesion).registrar(
            "COBRA_CUOTA", "CuotaMensual", cuota_id, "EXITO",
            f"{cuota.paciente.nombre} Q{cuota.monto:.2f}")
        flash(f"Cuota cobrada: {cuota.paciente.nombre}, Q{cuota.monto:,.2f}.", "success")
    except ErrorNegocio as error:
        flash(str(error), "danger")
    return volver("caja", anio=request.form.get("anio", type=int),
                  mes=request.form.get("mes", type=int))


# ================================================================ Reportes
REPORTES = {
    "costos-por-cita": {
        "titulo": "Costos por cita",
        "descripcion": "Costo de cada cita del interno, con exámenes y medicamentos.",
        "paciente": True, "roles": ["CAJA", "MEDICO_GENERAL", "MEDICO_ESPECIALISTA"]},
    "analisis-medico": {
        "titulo": "Análisis médico por paciente",
        "descripcion": "Ficha médica, motivo de ingreso, diagnósticos y medicamentos.",
        "paciente": True, "roles": ["MEDICO_GENERAL", "MEDICO_ESPECIALISTA", "ENFERMERIA"]},
    "cobros-por-paciente": {
        "titulo": "Cobros por paciente",
        "descripcion": "Cobros por rango de fechas con el detalle de cada gasto médico.",
        "paciente": True, "roles": ["CAJA"]},
    "pagos-fundacion": {
        "titulo": "Pagos a la fundación",
        "descripcion": "Lo facturado, lo pagado y la deuda actual con la fundación.",
        "paciente": False, "roles": ["CAJA"]},
    "entradas": {
        "titulo": "Entradas: donaciones y cobros",
        "descripcion": "Ingresos del asilo comparados con los gastos del periodo.",
        "paciente": False, "roles": ["CAJA"]},
    "examenes-por-paciente": {
        "titulo": "Exámenes realizados",
        "descripcion": "Exámenes de laboratorio solicitados y sus resultados.",
        "paciente": True, "roles": ["CAJA", "MEDICO_GENERAL", "MEDICO_ESPECIALISTA",
                                    "LABORATORIO"]},
    "medicamentos-por-paciente": {
        "titulo": "Medicamentos aplicados",
        "descripcion": "Medicamentos indicados y entregados al interno.",
        "paciente": True, "roles": ["CAJA", "MEDICO_GENERAL", "MEDICO_ESPECIALISTA",
                                    "FARMACIA"]},
}


@app.route("/reportes")
@requiere_rol()
def reportes():
    servicio = PacienteService(request.sesion)
    consultas = ConsultaService(request.sesion)
    rol = session.get("rol")
    disponibles = {clave: datos for clave, datos in REPORTES.items()
                   if rol == "ADMINISTRADOR" or rol in datos["roles"]}
    return render_template(
        "reportes.html", reportes=disponibles, pacientes=servicio.listar(),
        estado_servicios=consultas.estado_servicios())


@app.route("/reportes/<clave>")
@requiere_rol()
def ver_reporte(clave: str):
    definicion = REPORTES.get(clave)
    rol = session.get("rol")
    if definicion is None:
        flash("El reporte solicitado no existe.", "danger")
        return volver("reportes")
    if rol != "ADMINISTRADOR" and rol not in definicion["roles"]:
        AutenticacionService(request.sesion).registrar(
            "ACCESO_DENEGADO", "Reporte", None, "DENEGADO", f"Rol {rol} pidió {clave}")
        flash("Su rol no tiene permiso para consultar ese reporte.", "danger")
        return volver("reportes")

    consultas = ConsultaService(request.sesion)
    servicio = ReporteService(request.sesion, consultas.costos)
    paciente_id = request.args.get("paciente_id", type=int)
    desde = _fecha(request.args.get("desde"))
    hasta = _fecha(request.args.get("hasta"))

    if definicion["paciente"] and not paciente_id:
        flash("Seleccione el interno para generar ese reporte.", "warning")
        return volver("reportes")

    comunes = {"estado_servicios": consultas.estado_servicios(),
               "clave": clave, "definicion": definicion,
               "paciente_id": paciente_id,
               "desde": request.args.get("desde", ""),
               "hasta": request.args.get("hasta", ""),
               "pacientes": PacienteService(request.sesion).listar(),
               "generado": datetime.now()}

    if clave == "analisis-medico":
        datos = servicio.analisis_medico(paciente_id)
        return render_template("reporte_ficha.html", datos=datos, **comunes)

    generadores = {
        "costos-por-cita": lambda: servicio.costos_por_cita(paciente_id, desde, hasta),
        "cobros-por-paciente": lambda: servicio.cobros_por_paciente(paciente_id, desde, hasta),
        "pagos-fundacion": lambda: servicio.pagos_a_la_fundacion(desde, hasta),
        "entradas": lambda: servicio.entradas(desde, hasta),
        "examenes-por-paciente": lambda: servicio.examenes_por_paciente(paciente_id, desde, hasta),
        "medicamentos-por-paciente": lambda: servicio.medicamentos_por_paciente(
            paciente_id, desde, hasta),
    }
    datos = generadores[clave]()
    if servicio.sin_cobros:
        flash("El servicio de cobros no respondió: este reporte no incluye cargos.", "warning")
    return render_template("reporte_tabla.html", datos=datos, **comunes)


def preparar_base_de_datos() -> None:
    """Crea las tablas y carga los catalogos iniciales (solo si la base esta vacia)."""
    crear_tablas()
    cargar_datos_iniciales()


if __name__ == "__main__":
    # Solo para desarrollo local. En Docker la aplicacion corre con Gunicorn
    # (ver wsgi.py y el Dockerfile). El modo debug nunca se activa por defecto:
    # su consola permite ejecutar codigo en el servidor.
    preparar_base_de_datos()
    app.run(host="127.0.0.1", port=int(os.getenv("PUERTO", "8000")),
            debug=os.getenv("FLASK_DEBUG", "").lower() == "true")
