# Sistema de Administración del Asilo "Cabeza de Algodón"

Universidad Mariano Gálvez de Guatemala · Centro Regional de Mazatenango
Análisis y Diseño de Sistemas II · Ing. Angel Atilio Maltez C.
**Brandon Danilo Madrid Castillo — 3090-23-21158**

Versión actual: **1.2.0** (ver [CHANGELOG.md](CHANGELOG.md))

---

## 1. Qué es

Sistema web para administrar la información clínica, operativa y financiera del asilo:
expediente y ficha médica de cada interno, referencias a especialistas de la fundación,
visitas médicas con exámenes y medicamentos, cargos a la cuenta del familiar con el
descuento de la fundación, caja (cuotas, donaciones, gastos y pagos a la fundación),
los siete reportes del enunciado y el aviso por correo al familiar.

## 2. Arquitectura

Aplicación web en **tres capas lógicas** (presentación, lógica de negocio y acceso a datos)
construida como un monolito modular, del que se separaron **dos microservicios**.

| Componente | Tecnología | Puerto | Función |
|---|---|---|---|
| `app-base` | Python 3.11, Flask, SQLAlchemy, Gunicorn | 8000 | Aplicación web: expediente clínico, caja, reportes y seguridad. |
| `ms-costos` | Python 3.11, FastAPI | 8001 (interno) | Tarifas y cargos a la cuenta del familiar, con el descuento de la fundación. |
| `ms-notificaciones` | Python 3.11, FastAPI | 8002 (interno) | Redacta, envía y registra los correos al familiar. |
| `mysql` | MySQL 8.0 | 3306 (interno) | Una base por servicio: `db_asilo`, `db_costos`, `db_notificaciones`. |

Dentro de cada componente se respeta la misma separación:

| Capa lógica | `app-base` | Microservicios |
|---|---|---|
| Presentación | `app.py` (rutas) y `templates/` | `main.py` (API REST) y `schemas.py` |
| Lógica de negocio | `services.py`, `reportes.py`, `auth.py`, `validaciones.py`; paquete de integración `clientes.py` | `services.py` |
| Acceso a datos | `repository.py`, `database.py` | `repository.py`, `database.py` |
| (Entidades, usadas por las tres) | `models.py` | `models.py` |

Por qué dos microservicios y no más: el correo depende de un servidor SMTP externo que puede
fallar, y las tarifas cambian cuando la fundación negocia precios. Separados, una falla del
correo o de los cobros no impide registrar información clínica: el sistema la guarda y avisa
qué quedó pendiente.

## 3. Requisitos

- **Docker Desktop** (Windows o macOS) o Docker Engine con el plugin Compose (Linux).
- No hace falta instalar Python ni MySQL.

```bash
docker --version
docker compose version
```

## 4. Instalación y ejecución

```bash
git clone https://github.com/Bransly/asilo-cabeza-de-algodon.git
cd asilo-cabeza-de-algodon

# 1. Crear la configuración a partir de la plantilla
cp .env.example .env          # en Windows (PowerShell): copy .env.example .env

# 2. Editar .env y reemplazar TODOS los valores que dicen "cambiar".
#    Para generar claves aleatorias:
python -c "import secrets; print(secrets.token_hex(32))"

# 3. Levantar el sistema
docker compose up --build
```

La primera vez tarda de 2 a 4 minutos. Cuando el registro muestre `Booting worker` en
`app-base` y `Uvicorn running` en los dos microservicios, abrir **http://localhost:8000**.

| Dirección (solo en desarrollo) | Qué es |
|---|---|
| http://localhost:8000 | Sistema del asilo |
| http://localhost:8001/docs | Documentación de la API de costos (Swagger) |
| http://localhost:8002/docs | Documentación de la API de notificaciones (Swagger) |

Detener:

```bash
docker compose down        # conserva los datos
docker compose down -v     # borra también la base de datos
```

## 5. Primer ingreso

El sistema crea un usuario por rol. Las claves **no están en el código ni en este
repositorio**: son las que usted definió en `.env` (`CLAVE_INICIAL_ADMIN` y
`CLAVE_INICIAL_USUARIOS`). Si no las definió, el sistema genera una aleatoria y la muestra
una sola vez en el registro de `app-base` (`docker compose logs app-base`).

Son **claves temporales**: en el primer ingreso el sistema obliga a cada usuario a cambiarla
(mínimo 10 caracteres, con letras y números). Si alguien olvida su clave o queda bloqueado,
el administrador la restablece en **Usuarios**: el sistema genera una clave temporal nueva.

| Usuario | Rol | Accede a |
|---|---|---|
| `admin` | Administrador | Todo, incluida la bitácora de auditoría |
| `mgeneral` | Médico general | Expedientes, ficha médica y referencias |
| `especialista` | Médico especialista | Visitas, exámenes y recetas |
| `enfermeria` | Enfermería | Expedientes y medicamentos permanentes |
| `laboratorio` | Laboratorio | Bandeja de exámenes y carga de resultados |
| `farmacia` | Farmacia | Entrega de medicamentos |
| `caja` | Caja | Cobros, cuotas, donaciones, gastos y pagos a la fundación |
| `fundacion` | Fundación | Asignación de médico y horario |

Las personas de los datos de ejemplo son ficticias.

## 6. Desarrollo y producción

| | Desarrollo | Producción |
|---|---|---|
| Comando | `docker compose up --build` | `docker compose -f docker-compose.yml up -d --build` |
| Puertos publicados | 8000, y 3307/8001/8002 solo en `127.0.0.1` (archivo `docker-compose.override.yml`) | Solo 8000, detrás de un proxy inverso con HTTPS (443) |
| Servidor de la aplicación | Gunicorn, sin modo debug | Gunicorn, sin modo debug |
| `HTTPS` en `.env` | `false` | `true` (cookie `Secure` y HSTS) |

Los pasos completos para publicar en un servidor en la nube están en
[docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## 7. Pruebas

Con el sistema recién levantado (`docker compose down -v` y luego `up`):

```bash
pip install requests
# Use las mismas claves de su archivo .env
export CLAVE_INICIAL_ADMIN=...  CLAVE_INICIAL_USUARIOS=...  API_KEY_SERVICIOS=...
python pruebas/plan_pruebas.py --tolerancia
```

Ejecuta los casos **CP-01 a CP-77** (seguridad, validación de datos, flujo clínico, costos,
caja, reportes, tolerancia a fallas y administración de usuarios). Cada caso indica el requerimiento de la ERS que
verifica. El registro con fecha y resultado queda en `pruebas/resultados/`.

Después del plan, dos revisiones adicionales:

```bash
# Carga (RNF-20) y volumen (RNF-21)
python pruebas/carga.py carga --usuarios 20 --segundos 60
python pruebas/carga.py volumen --cargos 5000

# Accesibilidad WCAG 2.1 AA (RNF-22); requiere: pip install playwright,
# playwright install chromium y npm install axe-core
AXE_JS=node_modules/axe-core/axe.min.js python pruebas/accesibilidad.py
```

## 8. Reglas de negocio implementadas

- No se refiere a un interno sin ficha médica. Solo la fundación asigna médico y horario,
  y el médico debe ser de la especialidad solicitada.
- Una solicitud se convierte en visita médica una sola vez. La visita no se cierra sin
  diagnóstico ni con exámenes sin resultado.
- Consulta, examen y medicamento se cargan a la cuenta del familiar con el descuento de la
  fundación: `total = precio × cantidad × (1 − descuento/100)`, calculado con `Decimal` y
  redondeo comercial a centavos. El examen se cobra al solicitarlo y el medicamento al
  entregarlo.
- El familiar recibe dos correos: al crearse la solicitud (especialidad y motivo) y al
  asignarse el médico (nombre del médico y fecha de la cita).
- La deuda con la fundación es lo facturado por sus servicios menos los pagos que el asilo
  registró en caja. Un pago no puede superar la deuda.
- Todas las entradas se validan en el servidor (reglas RV-01 a RV-17 de la ERS).

## 9. Seguridad

| Control | Implementación |
|---|---|
| Contraseñas | Hash scrypt con sal por usuario. Política: mínimo 10 caracteres con letras y números. Cambio obligatorio de la clave inicial. |
| Ingreso | Mensaje genérico (no revela si el usuario existe o está bloqueado). Bloqueo de 15 minutos tras 5 intentos. |
| Sesión | Cookie firmada `HttpOnly`, `SameSite=Lax`, `Secure` con HTTPS. Vence a los 30 minutos sin actividad o a las 8 horas. Token de sesión guardado en el servidor: al cerrar sesión, una copia de la cookie deja de servir. |
| Autorización | Decorador `@requiere_rol` en cada ruta; el servidor siempre vuelve a validar. |
| Entre servicios | Cabecera `X-API-Key` con clave compartida; los microservicios responden 401 sin ella. |
| Encabezados HTTP | `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Cache-Control: no-store`. |
| Base de datos | Usuario técnico sin privilegios de administración. Consultas parametrizadas por el ORM. Dinero en `DECIMAL(10,2)`. |
| Secretos | Solo en `.env` (excluido por `.gitignore` y `.dockerignore`). La aplicación no arranca sin `SECRET_KEY` y `API_KEY_SERVICIOS`. |
| Auditoría | Tabla `bitacora`: usuario, rol, acción, entidad, resultado, IP y fecha. No guarda contraseñas ni el texto escrito como usuario en un ingreso fallido. |

## 10. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `Defina SECRET_KEY en .env` u otra variable | Falta crear `.env` o falta ese valor. Ver el paso 4. |
| `port is already allocated` | Otro programa usa el puerto. Cambie `PUERTO_APP` en `.env`. |
| Los servicios aparecen "sin conexión" | MySQL todavía arranca. Espere 30 segundos y recargue. |
| Cambié el `.env` o el modelo de datos y no se refleja | Las tablas y usuarios se crean solo la primera vez. Use `docker compose down -v` y vuelva a levantar (borra los datos). |
| Cambié código y no se refleja | `docker compose up --build`. |

Los errores conocidos y las limitaciones están documentados en el Manual de Usuario.

## 11. Documentación

La documentación de análisis, diseño, desarrollo e implementación se entrega por separado.
En este repositorio están la guía técnica de despliegue ([docs/DESPLIEGUE.md](docs/DESPLIEGUE.md)),
la descripción de los microservicios ([docs/MICROSERVICIOS.md](docs/MICROSERVICIOS.md)) y el
historial de versiones ([CHANGELOG.md](CHANGELOG.md)).
