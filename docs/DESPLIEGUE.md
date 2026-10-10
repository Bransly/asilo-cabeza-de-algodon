# Guía de despliegue en un servidor en la nube

Esta guía describe cómo publicar el sistema en un servidor virtual (VPS) con acceso
público por HTTPS, tal como se decidió en el Documento de Diseño Arquitectónico.
Para ejecutarlo en una computadora local basta con el README.

> El comando de Docker Compose levanta todo el sistema, **después** de completar los
> pasos 1 a 4. Esos pasos se hacen una sola vez por servidor.

## 1. Servidor

- VPS con Ubuntu Server 24.04 LTS, 2 vCPU, 4 GB de RAM y 40 GB de disco.
- Acceso por SSH **solo con llave** (sin contraseña) y usuario distinto de `root`.
- Firewall que permita únicamente los puertos 22 (SSH), 80 y 443:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80,443/tcp
sudo ufw enable
```

- Instalar Docker Engine y el plugin Compose (documentación oficial de Docker).

## 2. Dominio y HTTPS

1. Apuntar un dominio o subdominio (registro A) a la IP del servidor.
2. Instalar un proxy inverso que obtenga y renueve el certificado automáticamente.
   Con Caddy basta este archivo `/etc/caddy/Caddyfile`:

```
asilo.ejemplo.com {
    reverse_proxy 127.0.0.1:8000
}
```

3. En `.env`, publicar la aplicación solo hacia el proxy y activar HTTPS:

```env
PUERTO_APP=127.0.0.1:8000
HTTPS=true
```

Con `HTTPS=true` la cookie de sesión se marca `Secure` y se envía el encabezado HSTS.

## 3. Secretos

1. Clonar el repositorio en el servidor y crear `.env` a partir de `.env.example`.
2. Generar valores **nuevos** para producción (no reutilizar los de desarrollo):

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

   Variables: `MYSQL_ROOT_PASSWORD`, `DB_PASSWORD`, `SECRET_KEY`, `API_KEY_SERVICIOS`,
   `CLAVE_INICIAL_ADMIN`, `CLAVE_INICIAL_USUARIOS` y, si se usará correo real, las `SMTP_*`.
3. Proteger el archivo: `chmod 600 .env`.
4. Nunca subir `.env` al repositorio. Si una clave llegara a publicarse, se cambia de
   inmediato: borrarla en un commit nuevo no la elimina del historial.

## 4. Correo real (opcional)

Sin datos SMTP los correos quedan con estado `SIMULADA`. Para enviarlos con Gmail se crea
una *contraseña de aplicación* (requiere verificación en dos pasos) y se completa en `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USUARIO=cuenta@gmail.com
SMTP_PASSWORD=clave_de_aplicacion
CORREO_REMITENTE=cuenta@gmail.com
```

Después de levantar el sistema, crear una solicitud de prueba y verificar en el expediente
que el correo quede con estado `ENVIADA`.

## 5. Levantar en modo producción

```bash
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps
```

El parámetro `-f docker-compose.yml` hace que **no** se use `docker-compose.override.yml`,
de modo que MySQL y los microservicios no publican puertos: solo la aplicación (8000) queda
expuesta, y solo hacia el proxy.

Verificación:

| Comprobación | Resultado esperado |
|---|---|
| `https://asilo.ejemplo.com` | Pantalla de ingreso con candado válido |
| `curl -I http://IP:8001/salud` desde otra máquina | Sin respuesta (puerto cerrado) |
| `curl -I http://IP:3306` desde otra máquina | Sin respuesta (puerto cerrado) |
| `docker compose logs app-base` | `Booting worker`, sin errores |

Primer ingreso: cada usuario entra con su clave inicial y el sistema lo obliga a cambiarla.

## 6. Respaldos

Respaldo diario cifrado de las tres bases y prueba mensual de restauración.

```bash
# /opt/asilo/respaldo.sh  (programar con cron: 0 2 * * * /opt/asilo/respaldo.sh)
#!/bin/bash
set -euo pipefail
cd /opt/asilo/asilo-cabeza-de-algodon
source .env
FECHA=$(date +%F)
mkdir -p /opt/asilo/respaldos
docker compose exec -T -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql \
  mysqldump -uroot --single-transaction --databases db_asilo db_costos db_notificaciones \
  | gzip | openssl enc -aes-256-cbc -pbkdf2 -pass env:CLAVE_RESPALDO \
  > /opt/asilo/respaldos/asilo_$FECHA.sql.gz.enc
find /opt/asilo/respaldos -name "*.enc" -mtime +30 -delete
```

`CLAVE_RESPALDO` se define en el entorno del servidor, no en el repositorio. Los respaldos
nunca se guardan dentro de la carpeta del proyecto (`respaldos/` está en `.gitignore`).

Restauración de prueba (mensual, en un servidor de pruebas):

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:CLAVE_RESPALDO -in asilo_FECHA.sql.gz.enc \
  | gunzip | docker compose exec -T -e MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql mysql -uroot
```

Objetivos: pérdida máxima de datos de 24 horas (RPO) y restauración en menos de 4 horas (RTO).

## 7. Actualizar a una versión nueva

```bash
git pull
git checkout v1.2.0            # la etiqueta de la versión a instalar
docker compose -f docker-compose.yml up -d --build
```

Si la versión cambia el modelo de datos (ver CHANGELOG.md), hacer antes un respaldo.
El sistema crea tablas nuevas automáticamente, pero no modifica columnas existentes.

## 8. Lista de verificación antes de entregar

- [ ] `.env` con valores nuevos y `chmod 600`.
- [ ] `HTTPS=true` y certificado válido.
- [ ] Solo los puertos 22, 80 y 443 abiertos en el firewall.
- [ ] Levantado con `-f docker-compose.yml` (sin el archivo override).
- [ ] Claves iniciales cambiadas por cada usuario.
- [ ] Correo de prueba con estado `ENVIADA`, si se configuró SMTP.
- [ ] Primer respaldo generado y restaurado en una prueba.
