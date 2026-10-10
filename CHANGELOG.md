# Historial de versiones

Formato basado en *Keep a Changelog*. Versionado semántico: MAYOR.MENOR.PARCHE.
Cada versión se marca en Git con una etiqueta (`git tag v1.2.0`).

## [1.2.0] - 2026-10-10

Atiende el informe de revisión del SQA (hallazgos H-01 a H-11) y los pendientes del enunciado.

### Agregado
- Pagos del asilo a la fundación (RF-25): pestaña en Caja, deuda actual y reporte corregido.
- Segundo correo al familiar cuando la fundación asigna médico y horario, con el nombre del
  médico y la fecha de la cita.
- Reversión de un pago registrado por error, con motivo obligatorio y registro en bitácora (DEF-05).
- Validación de datos en el servidor (reglas RV-01 a RV-17): montos, porcentajes, edades,
  fechas, correos, longitudes y catálogos.
- Cambio obligatorio de la contraseña inicial y política de contraseñas.
- Clave de servicio (`X-API-Key`) entre la aplicación y los microservicios (DEF-06).
- Encabezados de seguridad HTTP y token de sesión en el servidor.
- Plan de pruebas automatizado CP-01 a CP-72 con registro de resultados.
- `docs/DESPLIEGUE.md`, `docs/MICROSERVICIOS.md` y este historial.

### Cambiado
- Dinero almacenado como `DECIMAL(10,2)` y calculado con `Decimal`.
- Credenciales fuera del código y del repositorio: todo se lee de `.env`.
- La aplicación corre con Gunicorn, sin modo debug.
- En producción solo se publica el puerto de la aplicación; los puertos 3307, 8001 y 8002
  quedan en `docker-compose.override.yml`, solo para desarrollo y solo en `127.0.0.1`.
- Los contenedores corren con un usuario sin privilegios.
- El mensaje de ingreso fallido es el mismo para usuario inexistente, cuenta bloqueada o inactiva.

### Corregido
- Una caída de un microservicio por error de conexión producía un error 500 en lugar de la
  advertencia prevista.
- Los reportes mostraban ceros sin aviso cuando el servicio de costos no respondía.

### Requiere
- Base de datos nueva (`docker compose down -v`): cambian tipos de columnas y se agregan tablas.
- Crear `.env` a partir de `.env.example`.

## [1.1.0] - 2026-09-16

### Agregado
- Módulo de caja: cuotas mensuales, donaciones y gastos.
- Los siete reportes del enunciado con filtros por interno y fechas.

## [1.0.0] - 2026-09-15

### Agregado
- Expediente clínico, solicitudes, visitas, laboratorio y farmacia.
- Microservicios de costos y de notificaciones.
- Autenticación, roles y bitácora de auditoría.
