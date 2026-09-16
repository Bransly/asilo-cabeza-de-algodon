# Microservicios — Sistema de Administración del Asilo "Cabeza de Algodón"

Universidad Mariano Gálvez de Guatemala · Centro Regional de Mazatenango
Análisis y Diseño de Sistemas II · Ing. Angel Atilio Maltez C.
**Brandon Danilo Madrid — 3090-23-21158**

---

## 1. Qué se entrega

Dos microservicios independientes, contenerizados, más una aplicación base que los consume.

| Componente | Puerto | Función |
|---|---|---|
| `app-base` | 8000 | Panel web del asilo. Consume los dos microservicios. |
| `ms-costos` | 8001 | Calcula y administra los cargos aplicando el descuento de la fundación. |
| `ms-notificaciones` | 8002 | Envía y registra el correo al familiar del paciente. |
| `mysql` | 3307 | Base de datos. Un esquema por microservicio. |

---

## 2. Por qué estos dos microservicios

El Documento de Diseño Arquitectónico del proyecto definió un **monolito modular** de tres capas. Esa decisión sigue vigente: el monolito Django es la aplicación base.

Lo que se hizo aquí es **extraer hacia servicios independientes los dos módulos que el propio documento ya listaba como dependencias externas**: *"Servicios de reportes y notificaciones invocados desde la lógica de aplicación"* (sección 4, Componentes y responsabilidades). Es una **arquitectura evolutiva**: se comienza con un monolito y se separa lo que tiene razones propias para cambiar y escalar.

Las razones concretas de la separación:

**`ms-costos`** — Las tarifas y los descuentos de la fundación cambian por negociación, no por cambios clínicos. Aislarlo permite modificar la política de precios sin tocar el expediente médico. Además es el único módulo que necesita cálculos monetarios exactos y auditables.

**`ms-notificaciones`** — Depende de un servidor SMTP externo, que es lento y falla. Si el envío de correo estuviera dentro del monolito, una caída del proveedor de correo bloquearía el registro de solicitudes médicas. Separado, si el correo falla la solicitud se registra igual y la bitácora deja constancia del fallo.

---

## 3. Requisitos

Solo **Docker Desktop**. No hace falta instalar Python ni MySQL.

Verificar:
```bash
docker --version
docker compose version
```

---

## 4. Cómo ejecutarlo

```bash
cd microservicios-asilo
docker compose up --build
```

La primera vez tarda entre 2 y 4 minutos (descarga MySQL y Python). Cuando aparezca `Uvicorn running` en los dos microservicios, abrir:

| Dirección | Qué es |
|---|---|
| http://localhost:8000 | Panel del asilo (aplicación base) |
| http://localhost:8001/docs | API de costos — Swagger interactivo |
| http://localhost:8002/docs | API de notificaciones — Swagger interactivo |

Para detener todo:
```bash
docker compose down          # conserva los datos
docker compose down -v       # borra también la base de datos
```

Ver los contenedores corriendo:
```bash
docker compose ps
docker compose logs -f ms-costos
```

---

## 5. Estructura de capas dentro de cada microservicio

Cada microservicio respeta **las mismas cuatro capas** definidas en el documento *Estructura de Capas del Proyecto*. Es un microservicio por fuera y un sistema en capas por dentro.

```
ms-costos/app/
├── main.py         → Capa de Presentación   (API REST, solo recibe HTTP)
├── services.py     → Capa de Lógica de Negocio (reglas del asilo)
├── repository.py   → Capa de Acceso a Datos  (patrón Repositorio)
├── models.py       → Capa de Entidades       (Tarifa, Cargo)
├── schemas.py      → DTOs de entrada y salida
└── database.py     → Conexión a MySQL
```

Regla que se cumple estrictamente: `main.py` **no** contiene SQL ni reglas; `services.py` **no** sabe que existe HTTP; solo `repository.py` toca la base de datos.

---

## 6. Regla de negocio implementada en `ms-costos`

Del enunciado: *"El costo de la cita, de los exámenes de laboratorio y farmacia son cargados a la cuenta del familiar siempre con el descuento que proporciona la fundación."*

```
subtotal = precio_base × cantidad
total    = subtotal × (1 − descuento_fundación / 100)
```

Ejemplo real del sistema:

| Servicio | Subtotal | Descuento | Total |
|---|---:|---:|---:|
| Consulta con especialista | Q350.00 | 35 % | Q227.50 |
| Hematología completa | Q120.00 | 50 % | Q60.00 |
| Losartán 50 mg × 30 | Q105.00 | 30 % | Q73.50 |
| **Estado de cuenta** | **Q575.00** | **ahorro Q214.00** | **Q361.00** |

Validaciones adicionales: no se cobra con una tarifa inactiva, no se paga dos veces el mismo cargo, y no se elimina un cargo ya pagado.

---

## 7. Endpoints

### ms-costos — puerto 8001

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/tarifas` | Catálogo de tarifas |
| POST | `/tarifas` | Crear tarifa |
| PUT | `/tarifas/{id}` | Actualizar tarifa |
| DELETE | `/tarifas/{id}` | Eliminar tarifa |
| POST | `/cargos` | Registrar cargo con descuento calculado |
| GET | `/cargos?paciente_id=1&estado=PENDIENTE` | Consultar cargos |
| PUT | `/cargos/{id}/pagar` | Marcar cargo como pagado |
| DELETE | `/cargos/{id}` | Eliminar cargo pendiente |
| GET | `/reportes/estado-cuenta/{paciente_id}` | Reporte de cobros por paciente |

### ms-notificaciones — puerto 8002

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/notificaciones/solicitud-medica` | Redacta, envía y registra el correo |
| GET | `/notificaciones?paciente_id=1` | Bitácora de correos |
| GET | `/notificaciones/{id}` | Detalle de una notificación |
| POST | `/notificaciones/{id}/reenviar` | Reintentar un envío fallido |
| DELETE | `/notificaciones/{id}` | Eliminar registro |

---

## 8. Correo real (opcional)

Sin credenciales SMTP, los correos se registran con estado `SIMULADA` y el sistema funciona igual — suficiente para la demostración.

Para enviar correos reales con Gmail, crear un archivo `.env` junto a `docker-compose.yml`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USUARIO=sucorreo@gmail.com
SMTP_PASSWORD=clave_de_aplicacion_de_16_letras
CORREO_REMITENTE=sucorreo@gmail.com
```

La contraseña **no** es la del correo: es una *contraseña de aplicación* que se genera en la cuenta de Google con verificación en dos pasos activada. Luego `docker compose up -d --build ms-notificaciones`. El estado pasará a `ENVIADA`.

---

## 9. Cómo integrarlo al proyecto Django real

El archivo `app-base/clientes.py` se copia tal cual al proyecto Django (por ejemplo en `asilo/servicios/clientes.py`) y se usa desde las vistas:

```python
from asilo.servicios.clientes import ClienteCostos, ClienteNotificaciones

def registrar_visita(request, visita_id):
    visita = VisitaMedica.objects.get(pk=visita_id)

    ClienteCostos().registrar_cargo({
        "paciente_id": visita.paciente.id,
        "paciente_nombre": visita.paciente.nombre_completo,
        "tarifa_id": request.POST["tarifa_id"],
        "cantidad": 1,
        "visita_id": visita.id,
    })
```

Django deja de calcular costos y de enviar correos: solo los solicita. Los modelos `Cobro` y las funciones de correo salen del monolito.

---

## 10. Despliegue en Kubernetes (opcional)

Con Docker Desktop y Kubernetes habilitado:

```bash
docker build -t ms-costos:1.0 ./ms-costos
docker build -t ms-notificaciones:1.0 ./ms-notificaciones
kubectl apply -f k8s/
kubectl get pods
```

Los manifiestos no son necesarios para cumplir la tarea; Docker Compose ya demuestra la contenerización y la orquestación.

---

## 11. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `port is already allocated` | Otro programa usa el puerto. Cambiar `8000:8000` por `8080:8000` en `docker-compose.yml`. |
| Los microservicios aparecen "sin conexión" | MySQL todavía arranca. Esperar 30 segundos y recargar. |
| `Can't connect to MySQL` en los logs | Normal en los primeros intentos; el reintento automático lo resuelve. |
| Cambié código y no se refleja | `docker compose up --build` (sin `--build` reutiliza la imagen anterior). |

---

## Seguridad (prototipo)

El sistema exige iniciar sesion. Cada rol ve unicamente sus modulos, y el
servidor vuelve a validar el permiso en **cada** peticion: ocultar un boton no
es un control de seguridad.

### Usuarios de prueba

| Usuario        | Contrasena   | Rol                  | Accede a                                   |
|----------------|--------------|----------------------|--------------------------------------------|
| `admin`        | `Admin2026*` | Administrador        | Todo, incluida la bitacora de auditoria    |
| `mgeneral`     | `Asilo2026*` | Medico general       | Expedientes, ficha medica y referencias    |
| `especialista` | `Asilo2026*` | Medico especialista  | Visitas, examenes y recetas                |
| `enfermeria`   | `Asilo2026*` | Enfermeria           | Expedientes y medicamentos permanentes     |
| `laboratorio`  | `Asilo2026*` | Laboratorio          | Bandeja de examenes y carga de resultados  |
| `farmacia`     | `Asilo2026*` | Farmacia             | Entrega de medicamentos                    |
| `caja`         | `Asilo2026*` | Caja                 | Cobros y estado de cuenta                  |
| `fundacion`    | `Asilo2026*` | Fundacion            | Asignacion de medico y horario             |

Son credenciales de demostracion. En produccion el administrador debe obligar a
cambiarlas en el primer ingreso.

### Controles implementados

| Control | Como esta implementado |
|---|---|
| Almacenamiento de contrasenas | Hash **scrypt** con sal aleatoria por usuario (`werkzeug.security`). La contrasena en claro nunca se guarda ni se escribe en la bitacora. |
| Verificacion | Comparacion en tiempo constante, para no filtrar informacion por el tiempo de respuesta. |
| Enumeracion de usuarios | Mensaje identico para usuario inexistente y contrasena incorrecta. |
| Fuerza bruta | Bloqueo de la cuenta por 15 minutos tras 5 intentos fallidos. |
| Sesion | Cookie firmada, `HttpOnly`, `SameSite=Lax`, vencimiento por inactividad a los 30 minutos y maximo de 8 horas. `Secure` se activa con la variable `HTTPS=true`. |
| Autorizacion | Decorador `@requiere_rol(...)` en el servidor, aplicado a las 24 rutas. |
| Redireccion abierta | Tras ingresar solo se acepta una ruta interna. |
| Inyeccion SQL | Consultas parametrizadas mediante el ORM; no hay SQL concatenado. |
| Auditoria | Tabla `bitacora`: usuario, rol, accion, entidad, resultado, detalle, IP y fecha. Registra ingresos, intentos fallidos, accesos denegados, altas y bajas de internos, cambios de ficha, pagos y eliminaciones de cargos. |
| Privilegio minimo en la base | Usuario tecnico `asilo` sin privilegios administrativos y sin acceso publico. |

### Verificacion

Las pruebas de `pruebas/seguridad.py` comprueban los 21 controles anteriores:
acceso sin sesion, mensajes genericos, bloqueo por intentos fallidos, denegacion
por rol en cada modulo, contenido de la bitacora y cierre de sesion.

---

## Modulo de caja

Accesible con el rol **Caja**. Tres pestanas:

- **Cuotas mensuales.** Se generan con un boton para el mes seleccionado, tomando el monto
  del expediente de cada interno activo. No se duplican si ya existen. Caja registra el cobro
  de cada una.
- **Donaciones.** Con el origen que pide el enunciado: empresa internacional, empresa
  nacional, gobierno y persona particular.
- **Gastos.** Egresos operativos por categoria: energia electrica, agua, alimentacion,
  mantenimiento, insumos, personal y otros.

Estos movimientos son tesoreria interna del asilo y viven en `db_asilo`. El microservicio
`ms-costos` administra unicamente lo que se cobra al familiar por los servicios de la
fundacion: consultas, examenes y medicamentos.

## Reportes

Los siete informes del enunciado, en `/reportes`. Cada uno admite filtro por interno y por
rango de fechas, y tiene boton de impresion que genera un PDF con membrete desde el navegador.

| Reporte | Qué muestra | Roles |
|---|---|---|
| Costos por cita | Costo de cada cita con consulta, examenes y medicamentos, y el ahorro de la fundacion | Caja, medicos |
| Analisis medico por paciente | Ficha medica, motivo de ingreso, diagnosticos, examenes y medicamentos | Medicos, enfermeria |
| Cobros por paciente | Cobros por rango de fechas con el detalle de cada gasto medico | Caja |
| Pagos a la fundacion | Facturado, pagado y deuda actual, agrupado por tipo de servicio | Caja |
| Entradas: donaciones y cobros | Donaciones, cuotas y cobros frente a los gastos del periodo | Caja |
| Examenes realizados | Examenes solicitados por interno y sus resultados | Caja, medicos, laboratorio |
| Medicamentos aplicados | Medicamentos indicados y entregados, mas los permanentes | Caja, medicos, farmacia |

El administrador accede a todos.

### Verificacion

`pruebas/caja_reportes.py` comprueba 36 puntos: el flujo clinico que alimenta los reportes,
el registro y las validaciones de caja, la generacion y cobro de cuotas sin duplicados, los
siete reportes, las cifras con descuento aplicado, el filtro por rango de fechas y la
restriccion por rol.
