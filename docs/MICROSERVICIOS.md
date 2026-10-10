# Microservicios

Los dos microservicios son internos: solo los llama la aplicación base, desde el servidor.
Toda petición (excepto `/salud`) exige la cabecera `X-API-Key` con el valor de
`API_KEY_SERVICIOS`; sin ella responden **401**. En desarrollo su documentación interactiva
está en `/docs`.

Cada uno tiene su propia base de datos y la misma estructura interna en capas:

```
app/
├── main.py         Presentación: API REST (FastAPI). Solo recibe y responde HTTP.
├── schemas.py      Contrato de entrada y salida (DTO) con sus validaciones.
├── services.py     Lógica de negocio. No conoce HTTP ni SQL.
├── repository.py   Acceso a datos (patrón Repositorio). Única capa que consulta la base.
├── models.py       Entidades.
├── database.py     Conexión a MySQL.
└── seguridad.py    Verificación de la clave de servicio.
```

## ms-costos (puerto interno 8001, base `db_costos`)

Calcula y administra los cargos a la cuenta del familiar con el descuento de la fundación.

```
subtotal = precio_base × cantidad                     (redondeado a centavos)
total    = subtotal × (1 − descuento_fundacion / 100) (redondeo comercial)
```

El cálculo usa `Decimal` y los montos se guardan en `DECIMAL(10,2)`. El precio y el
descuento se copian al cargo: si la tarifa cambia después, el cargo conserva su monto.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/salud` | Estado del servicio (sin clave) |
| GET | `/tarifas` | Catálogo de tarifas (`?solo_activas=true`) |
| GET | `/tarifas/{id}` | Una tarifa |
| POST | `/tarifas` | Crear tarifa |
| PUT | `/tarifas/{id}` | Actualizar tarifa |
| DELETE | `/tarifas/{id}` | Eliminar tarifa |
| GET | `/cargos` | Cargos (`?paciente_id=`, `?estado=PENDIENTE\|PAGADO`) |
| GET | `/cargos/{id}` | Un cargo |
| POST | `/cargos` | Registrar cargo con el descuento calculado |
| PUT | `/cargos/{id}/pagar` | Marcar como pagado |
| PUT | `/cargos/{id}/revertir-pago` | Volver a pendiente un pago registrado por error (exige `motivo`) |
| DELETE | `/cargos/{id}` | Eliminar un cargo pendiente |
| GET | `/reportes/estado-cuenta/{paciente_id}` | Facturado, pagado, ahorro y saldo |

Validaciones (respuesta 422): precio mayor que 0 y hasta Q99,999.99 con dos decimales como
máximo; descuento entre 0 y 100; cantidad entre 1 y 500.
Reglas (respuesta 400): no se cobra con una tarifa inactiva, no se paga dos veces, solo se
revierte un cargo pagado, no se elimina un cargo pagado.

## ms-notificaciones (puerto interno 8002, base `db_notificaciones`)

Redacta y envía el correo al familiar, y conserva el registro de cada envío aunque falle.

| Tipo de aviso | Cuándo | Contenido |
|---|---|---|
| `SOLICITUD_REGISTRADA` | El médico general crea la solicitud | Especialidad, motivo y estado del interno |
| `MEDICO_ASIGNADO` | La fundación asigna médico y horario | Nombre del médico, especialidad y fecha de la cita |

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/salud` | Estado del servicio (sin clave) |
| POST | `/notificaciones/solicitud-medica` | Redacta, envía y registra el aviso |
| GET | `/notificaciones` | Avisos enviados (`?paciente_id=`, `?estado=`) |
| GET | `/notificaciones/{id}` | Detalle de un aviso |
| POST | `/notificaciones/{id}/reenviar` | Reintentar un envío fallido |
| DELETE | `/notificaciones/{id}` | Eliminar un registro |

Estados del envío: `ENVIADA` (el servidor SMTP lo aceptó), `SIMULADA` (no hay SMTP
configurado) y `FALLIDA` (error al enviar; el detalle queda registrado).

## Comportamiento ante fallas

Si un microservicio no responde, la aplicación base guarda igual la información clínica
(solicitud, visita, entrega de medicamento) y muestra una advertencia indicando qué quedó
pendiente. El indicador de la barra lateral muestra si cada servicio está en línea.
Verificado por los casos CP-70 a CP-72.
