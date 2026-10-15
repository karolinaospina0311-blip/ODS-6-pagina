"""
Modelos SQL de EcoAgua (SQLAlchemy).

Tablas (modelo en Tercera Forma Normal):
  usuarios          Personal de la empresa con acceso al panel (rol administrador u operador).
  ciudadanos        Personas que reportan fugas (identificadas por su correo).
  reportes          Reportes de fugas enviados por los ciudadanos.
  fotografias       Fotografía de cada reporte, guardada dentro de la base de datos.
  historial_estados Cada cambio de estado de un reporte (quién, cuándo, de qué a qué).

El DDL equivalente está en database/schema.sql.
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import deferred
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _activar_llaves_foraneas_sqlite(conexion, _registro):
    # SQLite no valida llaves foráneas a menos que se active en cada conexión.
    if conexion.__class__.__module__.startswith("sqlite3"):
        cursor = conexion.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Estados permitidos. La clave es lo que se guarda en la BD; el valor es lo que se muestra.
ESTADOS = {
    "pendiente": "Pendiente",
    "en_proceso": "En proceso",
    "resuelto": "Resuelto",
}

TIPOS_FUGA = {
    "tuberia_calle": "Tubería rota en la calle o vía",
    "anden": "Agua brotando del andén o del piso",
    "medidor": "Fuga en medidor o acometida",
    "hidrante": "Hidrante dañado",
    "tanque_red": "Fuga en tanque o red pública",
    "otro": "Otro",
}

ROLES = {
    "administrador": "Administrador",
    "operador": "Operador",
}


def _lista_sql(valores):
    return ", ".join(f"'{v}'" for v in valores)


def ahora():
    # Se guarda en UTC sin zona para que funcione igual en SQLite, MySQL y PostgreSQL.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Usuario(db.Model):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(f"rol IN ({_lista_sql(ROLES)})", name="ck_usuarios_rol"),
    )

    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(60), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default="operador")
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=ahora)

    def fijar_password(self, password):
        self.password_hash = generate_password_hash(password)

    def verificar_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def es_administrador(self):
        return self.rol == "administrador"

    @property
    def rol_texto(self):
        return ROLES.get(self.rol, self.rol)


class Ciudadano(db.Model):
    __tablename__ = "ciudadanos"

    id = db.Column(db.Integer, primary_key=True)
    correo = db.Column(db.String(254), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    telefono = db.Column(db.String(30), nullable=True)
    fecha_registro = db.Column(db.DateTime, nullable=False, default=ahora)

    reportes = db.relationship("Reporte", back_populates="ciudadano")


class Reporte(db.Model):
    __tablename__ = "reportes"
    __table_args__ = (
        CheckConstraint(f"estado IN ({_lista_sql(ESTADOS)})", name="ck_reportes_estado"),
        CheckConstraint(f"tipo_fuga IN ({_lista_sql(TIPOS_FUGA)})", name="ck_reportes_tipo_fuga"),
        CheckConstraint("origen_ubicacion IN ('gps', 'mapa')", name="ck_reportes_origen"),
        CheckConstraint("latitud BETWEEN -90 AND 90", name="ck_reportes_latitud"),
        CheckConstraint("longitud BETWEEN -180 AND 180", name="ck_reportes_longitud"),
    )

    id = db.Column(db.Integer, primary_key=True)
    numero_seguimiento = db.Column(db.String(20), unique=True, nullable=False, index=True)
    ciudadano_id = db.Column(
        db.Integer, db.ForeignKey("ciudadanos.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    tipo_fuga = db.Column(db.String(30), nullable=False, default="otro")
    descripcion = db.Column(db.Text, nullable=False)

    latitud = db.Column(db.Float, nullable=False)
    longitud = db.Column(db.Float, nullable=False)
    origen_ubicacion = db.Column(db.String(10), nullable=False, default="mapa")  # gps | mapa
    precision_gps_m = db.Column(db.Float, nullable=True)
    barrio = db.Column(db.String(120), nullable=True)
    direccion_referencia = db.Column(db.String(255), nullable=True)

    estado = db.Column(db.String(20), nullable=False, default="pendiente", index=True)
    fecha_creacion = db.Column(db.DateTime, nullable=False, default=ahora, index=True)
    fecha_actualizacion = db.Column(db.DateTime, nullable=False, default=ahora, onupdate=ahora)

    # Marca los reportes creados con el comando de datos de prueba / ejemplo.
    es_prueba = db.Column(db.Boolean, nullable=False, default=False, index=True)

    ciudadano = db.relationship("Ciudadano", back_populates="reportes", lazy="joined")
    fotografia = db.relationship(
        "Fotografia", back_populates="reporte", uselist=False, cascade="all, delete-orphan"
    )
    historial = db.relationship(
        "HistorialEstado",
        back_populates="reporte",
        order_by="HistorialEstado.fecha",
        cascade="all, delete-orphan",
    )

    # Atajos usados por las plantillas.
    @property
    def nombre_ciudadano(self):
        return self.ciudadano.nombre if self.ciudadano else ""

    @property
    def correo(self):
        return self.ciudadano.correo if self.ciudadano else ""

    @property
    def telefono(self):
        return self.ciudadano.telefono if self.ciudadano else None

    @property
    def estado_texto(self):
        return ESTADOS.get(self.estado, self.estado)

    @property
    def tipo_fuga_texto(self):
        return TIPOS_FUGA.get(self.tipo_fuga, self.tipo_fuga)


class Fotografia(db.Model):
    """La imagen se guarda en la base de datos (no en disco) para que no se pierda
    cuando la plataforma en la nube reinicia el servidor."""
    __tablename__ = "fotografias"
    __table_args__ = (
        CheckConstraint("tamano_bytes > 0", name="ck_fotografias_tamano"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporte_id = db.Column(
        db.Integer, db.ForeignKey("reportes.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    tipo_mime = db.Column(db.String(30), nullable=False, default="image/jpeg")
    tamano_bytes = db.Column(db.Integer, nullable=False)
    # deferred: el contenido solo se lee de la BD cuando se pide la imagen.
    contenido = deferred(db.Column(db.LargeBinary, nullable=False))
    fecha_carga = db.Column(db.DateTime, nullable=False, default=ahora)

    reporte = db.relationship("Reporte", back_populates="fotografia")


class HistorialEstado(db.Model):
    __tablename__ = "historial_estados"
    __table_args__ = (
        CheckConstraint(f"estado_nuevo IN ({_lista_sql(ESTADOS)})", name="ck_historial_estado_nuevo"),
        CheckConstraint(
            f"estado_anterior IS NULL OR estado_anterior IN ({_lista_sql(ESTADOS)})",
            name="ck_historial_estado_anterior",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporte_id = db.Column(
        db.Integer, db.ForeignKey("reportes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    estado_anterior = db.Column(db.String(20), nullable=True)
    estado_nuevo = db.Column(db.String(20), nullable=False)
    nota = db.Column(db.String(500), nullable=True)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora)

    reporte = db.relationship("Reporte", back_populates="historial")
    usuario = db.relationship("Usuario")

    @property
    def estado_nuevo_texto(self):
        return ESTADOS.get(self.estado_nuevo, self.estado_nuevo)

    @property
    def estado_anterior_texto(self):
        return ESTADOS.get(self.estado_anterior, self.estado_anterior) if self.estado_anterior else "—"
