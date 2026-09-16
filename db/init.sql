-- Cada microservicio tiene su propia base de datos (principio de
-- "database per service"). Se ejecuta automaticamente la primera vez
-- que arranca el contenedor de MySQL.

CREATE DATABASE IF NOT EXISTS db_costos
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS db_notificaciones
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Esquema del monolito: expediente clinico (pacientes, ficha, solicitudes,
-- visitas, examenes y recetas).
CREATE DATABASE IF NOT EXISTS db_asilo
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Usuario tecnico con privilegios minimos, tal como se definio en el
-- Documento de Diseno Arquitectonico (seccion 6.1).
CREATE USER IF NOT EXISTS 'asilo'@'%' IDENTIFIED BY 'asilo123';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON db_costos.* TO 'asilo'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER
  ON db_notificaciones.* TO 'asilo'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX, ALTER, REFERENCES
  ON db_asilo.* TO 'asilo'@'%';

FLUSH PRIVILEGES;
