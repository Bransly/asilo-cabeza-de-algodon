# Guion del video — Avances del proyecto

**Sistema para Administración del Asilo de Ancianos Cabeza de Algodón**
Brandon Danilo Madrid — 3090-23-21158
Análisis y Diseño de Sistemas II · Ing. Angel Atilio Maltez C.

**Duración objetivo: 12 a 15 minutos.**

---

## Antes de grabar

1. `docker compose up --build` y esperar a que todo levante. Luego `docker compose down` y
   `docker compose up` otra vez: así en el video el arranque tarda 20 segundos y no 4 minutos.
2. Dejar la base **limpia** (`docker compose down -v` y volver a subir) para que la demostración
   se vea desde cero. La carga inicial deja 3 internos, 4 especialidades, 5 médicos y 3 enfermeros.
3. Pestañas abiertas: VS Code, `localhost:8000`, `localhost:8001/docs`, `localhost:8002/docs`,
   Docker Desktop.
4. Subir el tamaño de letra del editor y de la terminal. Lo que no se lee, no se califica.
5. Ensayar una vez el recorrido completo: dura unos 4 minutos.

---

## 0:00 – 0:45 · Presentación

> "Buenas tardes, ingeniero. Soy Brandon Danilo Madrid, carné 3090-23-21158. Este video muestra
> el avance del desarrollo del Sistema para la Administración del Asilo de Ancianos Cabeza de
> Algodón."

> "En la entrega anterior mostré los dos microservicios. En esta muestro el núcleo del sistema:
> el expediente clínico y el flujo completo de atención del interno, desde que el médico general
> lo evalúa hasta que el cargo llega a la cuenta del familiar."

---

## 0:45 – 2:00 · Arquitectura, en Docker Desktop

Mostrar los cuatro contenedores corriendo.

> "El sistema es un monolito modular en tres capas, como definí en el Documento de Diseño
> Arquitectónico, más dos microservicios que extraje: costos y notificaciones."

> "La aplicación base guarda el expediente clínico en su propia base de datos, db_asilo. Cada
> microservicio tiene la suya: db_costos y db_notificaciones. Eso es el patrón database per
> service: ningún servicio entra a la base de otro."

Mostrar `docker-compose.yml` y señalar las variables de entorno de `app-base`.

---

## 2:00 – 3:00 · Módulo de internos

Requisito del enunciado: *"llevar el registro de cada uno de sus internos"*.

En `localhost:8000` → pestaña **Internos**.

> "Aquí está el registro de internos. Antes estaban escritos en el código; ahora están en MySQL
> con su alta, edición y baja."

Registrar un interno nuevo en vivo. Señalar:

- El correo del familiar es obligatorio, porque el sistema debe notificarle cada solicitud médica.
- Al registrarlo se le crea automáticamente su **ficha médica**.
- La baja es lógica: el expediente clínico nunca se borra.

---

## 3:00 – 4:30 · Expediente y ficha médica

En el expediente del interno recién creado:

> "Esta es la ficha médica que pide el enunciado: psicopatología, padecimientos y alergias. Y aquí
> están los medicamentos permanentes, lo que el enunciado llama medicinas de cajón."

Llenar la ficha y agregar un medicamento permanente.

Bajar hasta **Historial médico** y explicar que ahí se acumulan todas las visitas con su
diagnóstico, exámenes y medicamentos.

---

## 4:30 – 5:30 · El médico general refiere al paciente

> "El asilo tiene un médico general que evalúa primero y determina a qué especialidad se remite al
> interno, asignando el enfermero que lo acompañará."

Crear la solicitud: especialidad, enfermero, motivo, estado del paciente.

Señalar dos cosas al enviarla:

1. El aviso verde dice que se notificó al familiar. Bajar y mostrar la **bitácora de correos**.
2. **Regla de negocio:** si el interno no tuviera ficha médica, el botón está deshabilitado.

> "El correo lo manda el microservicio de notificaciones. Si ese servicio se cae, la solicitud se
> guarda igual y solo queda la advertencia: por eso lo separé del monolito."

---

## 5:30 – 6:30 · Módulo de la fundación

Pestaña **Fundacion**.

> "El enunciado pide que las solicitudes aparezcan en un módulo que se le proporciona a la
> fundación, para que ellos asignen el horario y el médico. Este es ese módulo."

Asignar médico y fecha. Señalar la validación:

> "El sistema solo deja escoger médicos de la especialidad solicitada. Si intento asignar un
> traumatólogo a una referencia de cardiología, la regla lo rechaza."

Luego pulsar **Convertir en visita médica**.

> "Aquí la solicitud pasa a ser visita médica, tal como dice el enunciado. Y en ese mismo momento
> se carga la consulta a la cuenta del familiar."

---

## 6:30 – 8:30 · Visita médica

En la pantalla de la visita:

> "El médico especialista ve el motivo por el que fue referido y tiene a la izquierda la ficha
> médica completa del interno, para hacer el análisis de sus padecimientos."

1. Escribir **diagnóstico** y **observaciones**, guardar.
2. **Solicitar un examen** de laboratorio. Señalar el aviso: se cargó a la cuenta con el descuento.
3. **Indicar un medicamento** con cantidad e indicaciones de cómo tomarlo.

> "Fíjese en la diferencia: el examen se cobra al solicitarlo, pero el medicamento se cobra hasta
> que farmacia lo entrega. Si no se entrega, no se cobra."

---

## 8:30 – 9:30 · Laboratorio y farmacia

Pestaña **Laboratorio**:

> "El paciente llega al laboratorio, se identifica como interno del asilo y realiza los exámenes.
> Cuando están los resultados se colocan aquí y el médico puede consultarlos."

Cargar el resultado. Volver a la visita y mostrar que ya aparece.

Pestaña **Farmacia**: entregar el medicamento.

> "Al entregar, el sistema genera el cargo llamando al microservicio de costos."

---

## 9:30 – 11:00 · Todo llega a la cuenta del familiar

Volver al expediente del interno, bajar al **Estado de cuenta**.

> "Los tres cargos que se generaron solos durante la atención: la consulta, el examen y el
> medicamento. Cada uno con el descuento que da la fundación."

Mostrar un cálculo concreto: consulta de Q350 con 35% de descuento → Q227.50.

Mostrar el **historial médico** ya con la visita completa: fecha, motivo, médico y especialidad,
exámenes con resultados, diagnóstico, medicamentos y observaciones. Es exactamente la lista de
datos que pide el enunciado para la ficha médica.

Abrir `localhost:8001/docs` y ejecutar `GET /cargos` para probar que los cargos están en el
microservicio, no en el monolito.

---

## 11:00 – 12:30 · El código, por capas

En VS Code, abrir `app-base/`:

> "Respeté las cuatro capas del documento de Estructura de Capas del Proyecto."

- `models.py` → entidades del ERD: Paciente, FichaMedica, Solicitud, VisitaMedica, OrdenExamen…
- `repository.py` → patrón Repositorio; es la única capa que toca la base de datos.
- `services.py` → las reglas del asilo. Abrir `cerrar_visita` y leer la regla en voz alta: no se
  cierra una visita sin diagnóstico ni con exámenes pendientes de resultado.
- `app.py` → solo rutas. Ni SQL ni reglas de negocio.
- `clientes.py` → la única parte que sabe que los microservicios existen.

---

## 12:30 – 13:30 · Lo que sigue

Ser honesto con lo que falta; se nota mejor que ocultarlo.

> "Lo que sigue en el desarrollo es el login con roles, el módulo de caja con donaciones, cuotas y
> gastos, y los siete reportes del enunciado. La base ya está: los cargos se generan
> correctamente, así que los reportes saldrán de datos reales."

Cerrar agradeciendo.

---

## Si sobra tiempo

- **Cambio respecto al diseño original:** el documento decía Django; el desarrollo se hizo en Flask
  con SQLAlchemy. Mismo lenguaje, misma arquitectura de capas, menos peso. Conviene reconocerlo en
  el video y corregirlo en el documento de arquitectura.
- **Manejo de fallos:** con `docker compose stop ms-costos`, el panel muestra "Cobros: no
  disponible" y los botones que dependen de él se deshabilitan, pero el expediente sigue
  funcionando. Volver a levantarlo con `docker compose start ms-costos`.

---

## Sección adicional: seguridad (insertar después del minuto 2:00)

Con el sistema recién levantado, mostrar la **pantalla de login**.

> "El sistema exige autenticación. Las contraseñas se guardan con hash scrypt y
> sal aleatoria; no existe la contraseña en claro en ninguna parte del sistema."

1. Escribir mal la contraseña dos veces. Señalar que el mensaje es genérico, el
   mismo si el usuario existe o no, para no permitir enumerar cuentas.
2. Entrar como `caja`. Mostrar que el menú **no** tiene Laboratorio, Farmacia ni
   Bitácora, y que en el expediente sí aparecen los botones de cobro.
3. Entrar como `mgeneral`. Mostrar que ahora sí aparece "Referir a una especialidad"
   y que desaparecieron los botones de cobro.
4. Entrar como `admin` y abrir **Bitácora**.

> "Aquí está la auditoría: quién hizo qué, cuándo, sobre qué entidad y con qué
> resultado. Se registran los ingresos, los intentos fallidos y los accesos
> denegados. Fíjese en este registro de ACCESO_DENEGADO: es el intento que hizo
> el usuario de caja hace un momento."

Si hay tiempo, mostrar que la autorización está en el servidor y no solo en la
pantalla: con la sesión de caja abierta, enviar a mano una petición a una ruta de
médico y ver que el sistema la rechaza y la registra en la bitácora.

---

## Sección adicional: caja y reportes (insertar después del minuto 11:00)

Entrar como `caja`.

### Caja

> "El asilo se sostiene con donaciones y con la cuota mensual que pagan los familiares,
> y hay que fiscalizar contra los gastos. Este es el módulo de caja."

1. **Cuotas mensuales.** Pulsar el botón de generar las cuotas del mes. Señalar que el monto
   sale del expediente de cada interno y que si se pulsa otra vez no se duplican. Cobrar una.
2. **Donaciones.** Registrar una con origen "Empresa nacional". Mencionar los cuatro orígenes
   que pide el enunciado.
3. **Gastos.** Registrar el pago de energía eléctrica.

### Reportes

Ir a **Reportes**.

> "Aquí están los siete informes que pide el enunciado. Cada uno filtra por interno y por
> rango de fechas."

Mostrar dos o tres, no los siete, para no alargar:

- **Costos por cita:** señalar una fila y leer las cifras. La consulta de Q350 quedó en
  Q227.50 por el 35% de descuento de la fundación.
- **Entradas, donaciones y cobros:** mostrar el total de entradas frente a los gastos y la
  diferencia del periodo.
- **Análisis médico por paciente:** mostrar que trae la ficha, el motivo de ingreso, los
  diagnósticos y los medicamentos, tal como pide el enunciado.

Pulsar **Imprimir o guardar PDF** en cualquiera de ellos.

> "Cada reporte se imprime con membrete, la fecha de generación y el usuario que lo generó."

Cerrar la sección señalando el control de acceso:

> "Y los reportes también respetan los roles: el laboratorio no puede abrir el reporte de
> pagos a la fundación, porque no le corresponde información financiera."
