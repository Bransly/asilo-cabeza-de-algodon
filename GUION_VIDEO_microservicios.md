# Guion del video — Microservicios

**Duración objetivo: 12 a 14 minutos.** Los tiempos son referencia, no camisa de fuerza.

---

## Antes de grabar (5 minutos de preparación)

1. Ejecutar `docker compose up --build` y **esperar a que todo esté arriba**. Grabar con los contenedores ya construidos evita 3 minutos de espera muerta en cámara.
2. Luego ejecutar `docker compose down` y volver a `docker compose up` — así el arranque en el video tarda 20 segundos en lugar de 4 minutos, porque las imágenes ya están construidas.
3. Registrar 2 o 3 cargos de prueba en el paciente 1 para que el estado de cuenta ya tenga números.
4. Tener abiertas en pestañas: VS Code, `localhost:8000`, `localhost:8001/docs`, `localhost:8002/docs`, Docker Desktop.
5. Aumentar el tamaño de letra del editor y de la terminal. Lo que no se lee, no se califica.

---

## 0:00 – 1:00 · Presentación

> "Buenas tardes, ingeniero. Soy Brandon Danilo Madrid, carné 3090-23-21158. Este video corresponde a la tarea de microservicios del proyecto Sistema para la Administración del Asilo de Ancianos Cabeza de Algodón."

Mostrar el panel en `localhost:8000` unos segundos mientras se habla.

> "Desarrollé dos microservicios: uno de costos y cargos, y uno de notificaciones al familiar. Ambos están contenerizados en Docker y son consumidos por una aplicación base."

---

## 1:00 – 3:00 · Justificación arquitectónica ⚠️ *La parte más importante*

Abrir el Documento de Diseño Arquitectónico en pantalla, sección 4.

> "En mi documento de arquitectura definí un monolito modular de tres capas, y ahí mismo indiqué que los servicios de reportes y notificaciones se invocan desde la capa de aplicación como dependencias externas. Justamente esos dos módulos son los que extraje como microservicios."

> "Esto se llama arquitectura evolutiva: el monolito Django sigue siendo la aplicación base y conserva el expediente clínico, que es el núcleo del negocio; y se separan los módulos que tienen razones propias para cambiar."

Explicar las dos razones concretas:

- **Costos:** las tarifas y descuentos de la fundación cambian por negociación comercial, no por cambios clínicos. Separarlo permite modificar la política de precios sin tocar el expediente médico.
- **Notificaciones:** depende de un servidor SMTP externo que es lento y puede fallar. Si estuviera dentro del monolito, una caída del correo bloquearía el registro de solicitudes médicas. Separado, la solicitud se registra igual y el fallo queda en bitácora.

---

## 3:00 – 4:00 · Diagrama de la solución

Dibujar o mostrar este esquema:

```
        Navegador
            │
            ▼
   ┌─────────────────┐
   │  APLICACIÓN BASE │  :8000   (monolito Django / panel Flask)
   └────────┬─────────┘
            │  HTTP / JSON
      ┌─────┴──────┐
      ▼            ▼
┌───────────┐  ┌──────────────────┐
│ ms-costos │  │ ms-notificaciones│
│   :8001   │  │      :8002       │
└─────┬─────┘  └────────┬─────────┘
      │                 │
      ▼                 ▼
 db_costos      db_notificaciones     ← MySQL, un esquema por servicio
                        │
                        ▼
                  Servidor SMTP
```

Puntos a mencionar:
- Se comunican por **HTTP con JSON** (REST).
- **Base de datos por servicio**: `ms-costos` no puede leer las tablas de notificaciones; tiene que llamar a su API. Eso es lo que garantiza el desacoplamiento real.
- Los cuatro contenedores viven en una red Docker llamada `red-asilo` y se localizan por nombre de servicio, no por IP.

---

## 4:00 – 7:30 · Recorrido del código

Ir carpeta por carpeta en VS Code. **No leer línea por línea**; explicar la responsabilidad de cada archivo.

### 4:00 – 4:30 · Las cuatro capas

> "Cada microservicio respeta por dentro las mismas cuatro capas que definí en mi documento de Estructura de Capas."

Mostrar los archivos de `ms-costos/app/` y nombrar cada uno:
`main.py` presentación · `services.py` negocio · `repository.py` acceso a datos · `models.py` entidades.

> "La regla que se cumple estrictamente: main.py no tiene SQL ni reglas de negocio; services.py no sabe que existe HTTP; y solo el repositorio toca la base de datos."

### 4:30 – 6:00 · ms-costos

Abrir `models.py` — mostrar `Tarifa` y `Cargo` (10 segundos).

Abrir `services.py` y detenerse en el método `registrar()`:

> "Aquí está la regla central del enunciado: el costo se carga a la cuenta del familiar siempre con el descuento de la fundación. El subtotal es precio por cantidad, y el total es el subtotal menos el porcentaje de descuento."

Mostrar también `marcar_pagado()` y `eliminar()`:

> "Estas son validaciones de negocio: un cargo pagado no se vuelve a cobrar, y un cargo pagado no se puede eliminar porque es historial contable."

Abrir `repository.py` (20 segundos):

> "Patrón Repositorio, tal como lo documenté. Usa el ORM con consultas parametrizadas, no hay SQL concatenado, lo que previene inyección SQL."

Abrir `main.py` (20 segundos):

> "La API: GET, POST, PUT y DELETE. Cada endpoint solo traduce la petición HTTP y delega en el servicio."

### 6:00 – 7:00 · ms-notificaciones

Abrir `services.py` y mostrar `_redactar()` y `_enviar_correo()`:

> "El enunciado pide que se envíe un correo al familiar cuando se crea una solicitud médica, informando el estado del paciente y a qué médico fue referido. Este método arma ese correo con esos datos exactos."

> "Y algo importante: la notificación se guarda en base de datos **aunque el correo falle**. Esa bitácora es la evidencia de que se informó al familiar, y sirve para la auditoría que exige mi documento de arquitectura."

> "Si no hay credenciales SMTP configuradas, el correo se registra con estado SIMULADA. Así el sistema se puede demostrar sin depender de un servidor de correo."

### 7:00 – 7:30 · Aplicación base

Abrir `clientes.py`:

> "Aquí se concentra toda la comunicación con los microservicios. El resto de la aplicación no sabe que existe HTTP: solo llama métodos de Python. Esta misma clase se copia al proyecto Django para consumir los microservicios desde el monolito."

---

## 7:30 – 9:00 · Despliegue en contenedores

Abrir `docker-compose.yml`.

> "Cada microservicio tiene su propio Dockerfile: parte de una imagen ligera de Python, instala dependencias, copia el código y expone su puerto."

Abrir un `Dockerfile` (15 segundos) y volver al compose.

Explicar cuatro cosas del compose:
1. **Cuatro servicios**: MySQL, los dos microservicios y la app base.
2. **`depends_on` con `condition: service_healthy`** — los microservicios no arrancan hasta que MySQL responde.
3. **`URL_MS_COSTOS: http://ms-costos:8001`** — dentro de la red de Docker los servicios se llaman por nombre, no por `localhost`. Descubrimiento de servicios básico.
4. **Volumen `datos_mysql`** — los datos sobreviven aunque se apaguen los contenedores.

En la terminal:

```bash
docker compose down
docker compose up
```

Mientras arranca, mostrar Docker Desktop con los contenedores encendiéndose. Luego:

```bash
docker compose ps
```

> "Cuatro contenedores corriendo, cada uno con su puerto publicado."

---

## 9:00 – 12:30 · Demostración funcional

### 9:00 – 10:00 · Las APIs directamente

Abrir `localhost:8001/docs`.

> "FastAPI genera esta documentación interactiva automáticamente, lo que permite probar el microservicio sin la aplicación base."

Ejecutar en vivo:
- `GET /tarifas` → mostrar el catálogo.
- `POST /cargos` → registrar una consulta con especialista. **Señalar el resultado**: precio base 350, descuento 35 %, total 227.50.

Abrir `localhost:8002/docs` y mostrar `POST /notificaciones/solicitud-medica` con `GET /notificaciones` para ver la bitácora.

### 10:00 – 12:30 · El flujo completo desde la aplicación base

Ir a `localhost:8000`.

> "Este es el panel del asilo. Arriba a la derecha ve el estado de los dos microservicios: la aplicación base consulta el endpoint de salud de cada uno."

**Flujo 1 — Solicitud médica:**
1. Seleccionar a Rosa Elvira Pérez.
2. Llenar la solicitud: Cardiología, motivo "presión arterial elevada durante la evaluación del médico general".
3. Enviar → aparece la notificación en la bitácora con el correo completo redactado.

> "Aquí se cumple el requerimiento del enunciado: al crear la solicitud, el familiar recibe el correo con el estado del paciente y el médico al que fue referido."

**Flujo 2 — Cargos y estado de cuenta:**
1. Registrar consulta con especialista.
2. Registrar hematología completa.
3. Registrar 30 tabletas de Losartán.
4. Señalar el estado de cuenta: **facturado Q361.00, ahorro por la fundación Q214.00**.

> "Este es el reporte de cobros por paciente que exige el módulo de reportes, y muestra explícitamente cuánto ahorró el asilo gracias al convenio con la fundación."

5. Marcar un cargo como pagado → el saldo pendiente baja.

**Flujo 3 — Tolerancia a fallos** *(opcional pero deja excelente impresión)*

En la terminal:
```bash
docker compose stop ms-costos
```
Recargar el panel: el badge de `ms-costos` se pone en rojo, pero **el módulo de notificaciones sigue funcionando**.

> "Esta es la ventaja concreta de separar los servicios: la falla de uno no tumba al otro. En el monolito, un error en el cálculo de costos habría dejado sin servicio también a las notificaciones."

```bash
docker compose start ms-costos
```

---

## 12:30 – 13:30 · Integración con el proyecto y cierre

Abrir la sección 9 del README.

> "Para integrarlo al proyecto Django real, se copia la clase de clientes al proyecto y las vistas la usan. Django deja de calcular costos y de enviar correos: solamente los solicita a los microservicios."

Cierre:

> "En resumen: dos microservicios independientes, cada uno con su propia base de datos y sus cuatro capas internas; contenerizados con Docker y orquestados con Docker Compose; consumidos por una aplicación base; y ambos resuelven requerimientos textuales del enunciado del proyecto: el descuento de la fundación cargado a la cuenta del familiar, y la notificación al familiar al crear una solicitud médica. Gracias, ingeniero."

---

## Lista de verificación antes de subir el video

- [ ] Se ve el código de **ambos** microservicios
- [ ] Se explicó **por qué** esos dos y no otros
- [ ] Se mostró el `Dockerfile` y el `docker-compose.yml`
- [ ] Se ven los contenedores corriendo (`docker compose ps` o Docker Desktop)
- [ ] Se probaron las APIs directamente en Swagger
- [ ] Se demostró el flujo completo desde la aplicación base
- [ ] Se conectó cada microservicio con un requerimiento textual del enunciado
- [ ] El audio se escucha claro y la letra se lee
- [ ] Se dijo nombre y carné al inicio
