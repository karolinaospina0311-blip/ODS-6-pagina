-- =====================================================================
-- EcoAgua · Esquema de la base de datos
-- Motor en producción: PostgreSQL (Render). Desarrollo local: SQLite.
--
-- Tablas (Tercera Forma Normal):
--   usuarios           Personal de la empresa con acceso al panel (administrador / operador)
--   ciudadanos         Personas que reportan fugas (un registro por correo)
--   reportes           Reportes de fugas de agua
--   fotografias        Fotografía de cada reporte (1 a 1), guardada en la base de datos
--   historial_estados  Trazabilidad de cada cambio de estado (quién, cuándo, de qué a qué)
--
-- Relaciones:
--   ciudadanos 1 ── N reportes            (reportes.ciudadano_id, ON DELETE RESTRICT)
--   reportes   1 ── 0..1 fotografias      (fotografias.reporte_id UNIQUE, ON DELETE CASCADE)
--   reportes   1 ── N historial_estados   (historial_estados.reporte_id, ON DELETE CASCADE)
--   usuarios   1 ── N historial_estados   (historial_estados.usuario_id, ON DELETE SET NULL)
--
-- La aplicación crea estas tablas con:  flask --app backend/app init-db
-- También se pueden crear a mano ejecutando la sección del motor correspondiente.
-- =====================================================================

-- ============================ PostgreSQL ============================

CREATE TABLE usuarios (
	id SERIAL NOT NULL, 
	usuario VARCHAR(60) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	rol VARCHAR(20) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_usuarios_rol CHECK (rol IN ('administrador', 'operador'))
);
CREATE UNIQUE INDEX ix_usuarios_usuario ON usuarios (usuario);

CREATE TABLE ciudadanos (
	id SERIAL NOT NULL, 
	correo VARCHAR(254) NOT NULL, 
	nombre VARCHAR(120) NOT NULL, 
	telefono VARCHAR(30), 
	fecha_registro TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_ciudadanos_correo ON ciudadanos (correo);

CREATE TABLE reportes (
	id SERIAL NOT NULL, 
	numero_seguimiento VARCHAR(20) NOT NULL, 
	ciudadano_id INTEGER NOT NULL, 
	tipo_fuga VARCHAR(30) NOT NULL, 
	descripcion TEXT NOT NULL, 
	latitud FLOAT NOT NULL, 
	longitud FLOAT NOT NULL, 
	origen_ubicacion VARCHAR(10) NOT NULL, 
	precision_gps_m FLOAT, 
	barrio VARCHAR(120), 
	direccion_referencia VARCHAR(255), 
	estado VARCHAR(20) NOT NULL, 
	fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	fecha_actualizacion TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	es_prueba BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reportes_estado CHECK (estado IN ('pendiente', 'en_proceso', 'resuelto')), 
	CONSTRAINT ck_reportes_tipo_fuga CHECK (tipo_fuga IN ('tuberia_calle', 'anden', 'medidor', 'hidrante', 'tanque_red', 'otro')), 
	CONSTRAINT ck_reportes_origen CHECK (origen_ubicacion IN ('gps', 'mapa')), 
	CONSTRAINT ck_reportes_latitud CHECK (latitud BETWEEN -90 AND 90), 
	CONSTRAINT ck_reportes_longitud CHECK (longitud BETWEEN -180 AND 180), 
	FOREIGN KEY(ciudadano_id) REFERENCES ciudadanos (id) ON DELETE RESTRICT
);
CREATE INDEX ix_reportes_ciudadano_id ON reportes (ciudadano_id);
CREATE INDEX ix_reportes_es_prueba ON reportes (es_prueba);
CREATE INDEX ix_reportes_estado ON reportes (estado);
CREATE INDEX ix_reportes_fecha_creacion ON reportes (fecha_creacion);
CREATE UNIQUE INDEX ix_reportes_numero_seguimiento ON reportes (numero_seguimiento);

CREATE TABLE fotografias (
	id SERIAL NOT NULL, 
	reporte_id INTEGER NOT NULL, 
	tipo_mime VARCHAR(30) NOT NULL, 
	tamano_bytes INTEGER NOT NULL, 
	contenido BYTEA NOT NULL, 
	fecha_carga TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_fotografias_tamano CHECK (tamano_bytes > 0), 
	FOREIGN KEY(reporte_id) REFERENCES reportes (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_fotografias_reporte_id ON fotografias (reporte_id);

CREATE TABLE historial_estados (
	id SERIAL NOT NULL, 
	reporte_id INTEGER NOT NULL, 
	usuario_id INTEGER, 
	estado_anterior VARCHAR(20), 
	estado_nuevo VARCHAR(20) NOT NULL, 
	nota VARCHAR(500), 
	fecha TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_historial_estado_nuevo CHECK (estado_nuevo IN ('pendiente', 'en_proceso', 'resuelto')), 
	CONSTRAINT ck_historial_estado_anterior CHECK (estado_anterior IS NULL OR estado_anterior IN ('pendiente', 'en_proceso', 'resuelto')), 
	FOREIGN KEY(reporte_id) REFERENCES reportes (id) ON DELETE CASCADE, 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
CREATE INDEX ix_historial_estados_reporte_id ON historial_estados (reporte_id);
CREATE INDEX ix_historial_estados_usuario_id ON historial_estados (usuario_id);

-- ============================== SQLite ==============================
-- (Descomente esta sección si usa SQLite en lugar de PostgreSQL)

-- CREATE TABLE usuarios (
-- 	id INTEGER NOT NULL, 
-- 	usuario VARCHAR(60) NOT NULL, 
-- 	nombre VARCHAR(120) NOT NULL, 
-- 	password_hash VARCHAR(255) NOT NULL, 
-- 	rol VARCHAR(20) NOT NULL, 
-- 	activo BOOLEAN NOT NULL, 
-- 	fecha_creacion DATETIME NOT NULL, 
-- 	PRIMARY KEY (id), 
-- 	CONSTRAINT ck_usuarios_rol CHECK (rol IN ('administrador', 'operador'))
-- );
-- CREATE UNIQUE INDEX ix_usuarios_usuario ON usuarios (usuario);

-- CREATE TABLE ciudadanos (
-- 	id INTEGER NOT NULL, 
-- 	correo VARCHAR(254) NOT NULL, 
-- 	nombre VARCHAR(120) NOT NULL, 
-- 	telefono VARCHAR(30), 
-- 	fecha_registro DATETIME NOT NULL, 
-- 	PRIMARY KEY (id)
-- );
-- CREATE UNIQUE INDEX ix_ciudadanos_correo ON ciudadanos (correo);

-- CREATE TABLE reportes (
-- 	id INTEGER NOT NULL, 
-- 	numero_seguimiento VARCHAR(20) NOT NULL, 
-- 	ciudadano_id INTEGER NOT NULL, 
-- 	tipo_fuga VARCHAR(30) NOT NULL, 
-- 	descripcion TEXT NOT NULL, 
-- 	latitud FLOAT NOT NULL, 
-- 	longitud FLOAT NOT NULL, 
-- 	origen_ubicacion VARCHAR(10) NOT NULL, 
-- 	precision_gps_m FLOAT, 
-- 	barrio VARCHAR(120), 
-- 	direccion_referencia VARCHAR(255), 
-- 	estado VARCHAR(20) NOT NULL, 
-- 	fecha_creacion DATETIME NOT NULL, 
-- 	fecha_actualizacion DATETIME NOT NULL, 
-- 	es_prueba BOOLEAN NOT NULL, 
-- 	PRIMARY KEY (id), 
-- 	CONSTRAINT ck_reportes_estado CHECK (estado IN ('pendiente', 'en_proceso', 'resuelto')), 
-- 	CONSTRAINT ck_reportes_tipo_fuga CHECK (tipo_fuga IN ('tuberia_calle', 'anden', 'medidor', 'hidrante', 'tanque_red', 'otro')), 
-- 	CONSTRAINT ck_reportes_origen CHECK (origen_ubicacion IN ('gps', 'mapa')), 
-- 	CONSTRAINT ck_reportes_latitud CHECK (latitud BETWEEN -90 AND 90), 
-- 	CONSTRAINT ck_reportes_longitud CHECK (longitud BETWEEN -180 AND 180), 
-- 	FOREIGN KEY(ciudadano_id) REFERENCES ciudadanos (id) ON DELETE RESTRICT
-- );
-- CREATE INDEX ix_reportes_ciudadano_id ON reportes (ciudadano_id);
-- CREATE INDEX ix_reportes_es_prueba ON reportes (es_prueba);
-- CREATE INDEX ix_reportes_estado ON reportes (estado);
-- CREATE INDEX ix_reportes_fecha_creacion ON reportes (fecha_creacion);
-- CREATE UNIQUE INDEX ix_reportes_numero_seguimiento ON reportes (numero_seguimiento);

-- CREATE TABLE fotografias (
-- 	id INTEGER NOT NULL, 
-- 	reporte_id INTEGER NOT NULL, 
-- 	tipo_mime VARCHAR(30) NOT NULL, 
-- 	tamano_bytes INTEGER NOT NULL, 
-- 	contenido BLOB NOT NULL, 
-- 	fecha_carga DATETIME NOT NULL, 
-- 	PRIMARY KEY (id), 
-- 	CONSTRAINT ck_fotografias_tamano CHECK (tamano_bytes > 0), 
-- 	FOREIGN KEY(reporte_id) REFERENCES reportes (id) ON DELETE CASCADE
-- );
-- CREATE UNIQUE INDEX ix_fotografias_reporte_id ON fotografias (reporte_id);

-- CREATE TABLE historial_estados (
-- 	id INTEGER NOT NULL, 
-- 	reporte_id INTEGER NOT NULL, 
-- 	usuario_id INTEGER, 
-- 	estado_anterior VARCHAR(20), 
-- 	estado_nuevo VARCHAR(20) NOT NULL, 
-- 	nota VARCHAR(500), 
-- 	fecha DATETIME NOT NULL, 
-- 	PRIMARY KEY (id), 
-- 	CONSTRAINT ck_historial_estado_nuevo CHECK (estado_nuevo IN ('pendiente', 'en_proceso', 'resuelto')), 
-- 	CONSTRAINT ck_historial_estado_anterior CHECK (estado_anterior IS NULL OR estado_anterior IN ('pendiente', 'en_proceso', 'resuelto')), 
-- 	FOREIGN KEY(reporte_id) REFERENCES reportes (id) ON DELETE CASCADE, 
-- 	FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE SET NULL
-- );
-- CREATE INDEX ix_historial_estados_reporte_id ON historial_estados (reporte_id);
-- CREATE INDEX ix_historial_estados_usuario_id ON historial_estados (usuario_id);
