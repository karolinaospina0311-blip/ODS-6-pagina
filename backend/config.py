"""
Configuración de EcoAgua.

Todos los valores sensibles o dependientes del despliegue se leen de variables
de entorno (ver .env.example y README.md). Para desarrollo local funcionan los
valores por defecto:
  - Base de datos SQLite en instance/ecoagua.db
  - Clave secreta generada automáticamente y guardada en instance/secret_key

En producción (Render) se usa PostgreSQL mediante DATABASE_URL.
"""
import os
import secrets

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
RAIZ_DIR = os.path.dirname(BACKEND_DIR)
FRONTEND_DIR = os.path.join(RAIZ_DIR, "frontend")
INSTANCE_DIR = os.path.join(RAIZ_DIR, "instance")


def _cargar_env():
    """Carga un archivo .env de la raíz si existe (solo desarrollo; nunca se sube a GitHub)."""
    ruta = os.path.join(RAIZ_DIR, ".env")
    if not os.path.isfile(ruta):
        return
    with open(ruta, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env()


def _clave_secreta():
    clave = os.environ.get("ECOAGUA_SECRET_KEY")
    if clave:
        return clave
    # Desarrollo: se genera una vez y se reutiliza para no cerrar sesiones al reiniciar.
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    ruta = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(ruta, encoding="utf-8") as f:
        return f.read().strip()


def _url_base_datos():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "ecoagua.db")
    # Rutas SQLite relativas (sqlite:///database/ecoagua.db) se toman desde la raíz del proyecto.
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        ruta = url[len("sqlite:///"):]
        if ruta and ruta != ":memory:" and not os.path.isabs(ruta) and not (len(ruta) > 1 and ruta[1] == ":"):
            url = "sqlite:///" + os.path.join(RAIZ_DIR, ruta).replace("\\", "/")
    # Render entrega "postgres://..." o "postgresql://..."; SQLAlchemy necesita el driver psycopg 3.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def _float_env(nombre, defecto):
    try:
        return float(os.environ.get(nombre, defecto))
    except ValueError:
        return float(defecto)


class Config:
    SECRET_KEY = _clave_secreta()

    SQLALCHEMY_DATABASE_URI = _url_base_datos()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Evita errores por conexiones cerradas por el servidor de base de datos (planes gratuitos).
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    MAX_FOTO_MB = _float_env("ECOAGUA_MAX_FOTO_MB", 8)
    # Límite total de la petición (foto + campos) con un margen.
    MAX_CONTENT_LENGTH = int((MAX_FOTO_MB + 1) * 1024 * 1024)
    FOTO_OBLIGATORIA = os.environ.get("ECOAGUA_FOTO_OBLIGATORIA", "1") == "1"

    MAPA_LAT = _float_env("ECOAGUA_MAPA_LAT", 4.5709)
    MAPA_LNG = _float_env("ECOAGUA_MAPA_LNG", -74.2973)
    MAPA_ZOOM = int(_float_env("ECOAGUA_MAPA_ZOOM", 6))

    # "1" cuando la app está detrás de un proxy HTTPS (Render): usa la IP real y el esquema https.
    DETRAS_DE_PROXY = os.environ.get("ECOAGUA_PROXY", "0") == "1"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("ECOAGUA_COOKIE_SEGURA", "0") == "1"
