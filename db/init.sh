#!/bin/bash
# ---------------------------------------------------------------------------
# Inicializacion de MySQL. Se ejecuta automaticamente la PRIMERA vez que
# arranca el contenedor (cuando el volumen de datos esta vacio).
#
# - Una base de datos por servicio (patron "database per service").
# - Un usuario tecnico con privilegios minimos, sin permisos de
#   administracion, tal como define el Documento de Diseno Arquitectonico.
#
# La contrasena del usuario tecnico NO esta escrita aqui: se toma de la
# variable DB_PASSWORD del archivo .env.
# ---------------------------------------------------------------------------
set -euo pipefail

: "${DB_USER:?Falta DB_USER en el archivo .env}"
: "${DB_PASSWORD:?Falta DB_PASSWORD en el archivo .env}"

mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS db_asilo
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS db_costos
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS db_notificaciones
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';

-- Solo lo necesario para operar y crear sus tablas. Sin DROP, sin GRANT,
-- sin acceso a otras bases.
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON db_asilo.* TO '${DB_USER}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON db_costos.* TO '${DB_USER}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON db_notificaciones.* TO '${DB_USER}'@'%';

FLUSH PRIVILEGES;
SQL

echo "[init] Bases db_asilo, db_costos y db_notificaciones creadas para ${DB_USER}"
