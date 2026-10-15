"""
EcoAgua · servidor web (Flask).

Sirve la página pública existente (index.html, styles.css, script.js) sin
modificar su funcionamiento, y agrega:
  - API pública para crear reportes y consultar su estado.
  - Panel administrativo protegido (ver admin.py).

Ejecutar en desarrollo (desde la raíz del proyecto):
    flask --app backend/app init-db
    flask --app backend/app crear-usuario --rol administrador
    flask --app backend/app run --debug

En producción (Render):
    gunicorn --chdir backend app:app
"""


# --- Botón ▶ de VS Code: si se ejecuta este archivo con un Python que no es el del
# entorno virtual del proyecto (.venv), se vuelve a lanzar con el Python correcto.
if __name__ == "__main__":
    import os as _os, subprocess as _sp, sys as _sys
    _venv = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), ".venv")
    _py = _os.path.join(_venv, "Scripts", "python.exe") if _os.name == "nt" else _os.path.join(_venv, "bin", "python")
    if _os.path.isfile(_py) and _os.path.normcase(_os.path.abspath(_sys.prefix)) != _os.path.normcase(_venv):
        try:
            _sys.exit(_sp.call([_py, _os.path.abspath(__file__), *_sys.argv[1:]]))
        except KeyboardInterrupt:
            _sys.exit(0)



import os
import random
from datetime import timedelta
from io import BytesIO

import click
from flask import Flask, abort, jsonify, request, send_file, send_from_directory, url_for

from admin import admin_bp
from datos_ejemplo import generar_datos_ejemplo
from config import FRONTEND_DIR, INSTANCE_DIR, Config
from models import ESTADOS, ROLES, TIPOS_FUGA, Ciudadano, Reporte, Usuario, ahora, db
from servicios import (
    ErrorValidacion,
    LimitadorSimple,
    cambiar_estado,
    contenido_foto,
    crear_reporte,
    normalizar_seguimiento,
    procesar_foto,
    reporte_publico,
    validar_formulario_reporte,
)

# Archivos de la página pública original que se sirven tal cual.
ARCHIVOS_PUBLICOS = {"index.html", "styles.css", "script.js", "reportes.js"}

limite_reportes = LimitadorSimple(maximo=10, ventana_segundos=3600)
limite_consultas = LimitadorSimple(maximo=60, ventana_segundos=60)


def create_app(config_obj=Config):
    app = Flask(__name__,
                static_folder=os.path.join(FRONTEND_DIR, "static"), static_url_path="/static",
                template_folder=os.path.join(FRONTEND_DIR, "templates"))
    app.config.from_object(config_obj)
    os.makedirs(INSTANCE_DIR, exist_ok=True)

    if app.config.get("DETRAS_DE_PROXY"):
        # Render atiende HTTPS y reenvía la petición: así Flask ve la IP real y el esquema https.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    app.register_blueprint(admin_bp)
    registrar_rutas_publicas(app)
    registrar_comandos(app)

    with app.app_context():
        db.create_all()

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        # OpenStreetMap exige saber el origen de las peticiones de mapas; esta política
        # envía solo el dominio del sitio (nunca la ruta completa) a otros servidores.
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(413)
    def demasiado_grande(_e):
        mb = app.config["MAX_FOTO_MB"]
        return jsonify(ok=False, errores={"foto": f"La fotografía supera el tamaño máximo de {mb:g} MB."}), 413

    return app


def _ip():
    # Con ECOAGUA_PROXY=1 (Render) ProxyFix hace que remote_addr sea la IP real del ciudadano.
    return request.remote_addr or "desconocida"


def registrar_rutas_publicas(app):

    # ---------------- página pública existente ----------------
    @app.get("/")
    def inicio():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<nombre>")
    def archivo_publico(nombre):
        if nombre not in ARCHIVOS_PUBLICOS:
            abort(404)
        return send_from_directory(FRONTEND_DIR, nombre)

    # ---------------- configuración para el formulario ----------------
    @app.get("/api/config")
    def api_config():
        return jsonify(
            mapa={"lat": app.config["MAPA_LAT"], "lng": app.config["MAPA_LNG"],
                  "zoom": app.config["MAPA_ZOOM"]},
            foto_obligatoria=app.config["FOTO_OBLIGATORIA"],
            max_foto_mb=app.config["MAX_FOTO_MB"],
            tipos_fuga=[{"valor": k, "texto": v} for k, v in TIPOS_FUGA.items()],
        )

    # ---------------- crear reporte ----------------
    @app.post("/api/reportes")
    def api_crear_reporte():
        # Campo trampa: los humanos no lo ven; los bots suelen llenarlo.
        if request.form.get("sitio_web"):
            return jsonify(ok=False, errores={"general": "No se pudo registrar el reporte."}), 400
        foto = request.files.get("foto")
        try:
            datos = validar_formulario_reporte(request.form, foto, app.config["FOTO_OBLIGATORIA"])
            # Solo cuentan los envíos válidos, para no bloquear a quien se equivoca llenando el formulario.
            if not limite_reportes.permitido(_ip()):
                return jsonify(ok=False, errores={"general": "Has enviado muchos reportes en poco tiempo. Intenta de nuevo en una hora."}), 429
            foto_bytes = None
            if foto is not None and foto.filename:
                foto_bytes = procesar_foto(foto, app.config["MAX_FOTO_MB"])
        except ErrorValidacion as e:
            return jsonify(ok=False, errores=e.errores), 400

        try:
            reporte = crear_reporte(datos, foto_bytes)
        except Exception:
            db.session.rollback()
            app.logger.exception("Error guardando reporte")
            return jsonify(ok=False, errores={"general": "No se pudo guardar el reporte. Intenta de nuevo."}), 500

        return jsonify(ok=True, numero_seguimiento=reporte.numero_seguimiento), 201

    # ---------------- consultar estado ----------------
    @app.get("/api/reportes/<numero>")
    def api_consultar(numero):
        if not limite_consultas.permitido(_ip()):
            return jsonify(ok=False, error="Demasiadas consultas. Espera un minuto."), 429
        numero = normalizar_seguimiento(numero)
        if not numero:
            return jsonify(ok=False, error="El número debe tener el formato ECO-2026-00001."), 400
        reporte = Reporte.query.filter_by(numero_seguimiento=numero).first()
        if not reporte:
            return jsonify(ok=False, error="No encontramos un reporte con ese número. Revisa que esté bien escrito."), 404
        url_foto = url_for("foto_publica", numero=numero) if reporte.fotografia else None
        return jsonify(ok=True, reporte=reporte_publico(reporte, url_foto))

    @app.get("/api/reportes/<numero>/foto")
    def foto_publica(numero):
        numero = normalizar_seguimiento(numero)
        reporte = Reporte.query.filter_by(numero_seguimiento=numero).first() if numero else None
        contenido = contenido_foto(reporte)
        if not contenido:
            abort(404)
        return send_file(BytesIO(contenido), mimetype="image/jpeg", max_age=3600)


# ---------------------------------------------------------------- comandos CLI

def guardar_usuario_cli(usuario, nombre, rol, password):
    usuario = usuario.strip().lower()
    if not usuario or len(usuario) > 60:
        raise ValueError("El usuario es obligatorio (máximo 60 caracteres).")
    if rol not in ROLES:
        raise ValueError("Rol no válido.")
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres.")
    existente = Usuario.query.filter_by(usuario=usuario).first()
    if existente:
        existente.nombre = nombre.strip()
        existente.rol = rol
        existente.activo = True
        accion = "actualizado"
    else:
        existente = Usuario(usuario=usuario, nombre=nombre.strip(), rol=rol)
        db.session.add(existente)
        accion = "creado"
    existente.fijar_password(password)
    db.session.commit()
    return accion


def registrar_comandos(app):

    @app.cli.command("init-db")
    def init_db():
        """Crea las tablas si no existen (no borra datos)."""
        db.create_all()
        click.echo(f"Tablas listas en: {app.config['SQLALCHEMY_DATABASE_URI']}")

    @app.cli.command("crear-usuario")
    @click.option("--usuario", prompt="Usuario")
    @click.option("--nombre", prompt="Nombre completo")
    @click.option("--rol", type=click.Choice(list(ROLES)), prompt="Rol", default="operador",
                  show_default=True)
    @click.password_option("--password", prompt="Contraseña (mínimo 10 caracteres)")
    def crear_usuario(usuario, nombre, rol, password):
        """Crea un usuario del panel o cambia la contraseña/rol de uno existente."""
        try:
            accion = guardar_usuario_cli(usuario, nombre, rol, password)
        except ValueError as e:
            raise click.ClickException(str(e))
        click.echo(f"Usuario «{usuario.strip().lower()}» ({ROLES[rol]}) {accion}.")

    @app.cli.command("sembrar")
    def sembrar():
        """Crea los usuarios de prueba y los datos de ejemplo definidos en variables de entorno.

        Se ejecuta en cada arranque en Render y no duplica nada:
          ECOAGUA_ADMIN_USUARIO / ECOAGUA_ADMIN_PASSWORD       -> usuario administrador
          ECOAGUA_OPERADOR_USUARIO / ECOAGUA_OPERADOR_PASSWORD -> usuario regular (operador)
          ECOAGUA_DATOS_EJEMPLO=1 -> crea 30 reportes de ejemplo si la base está vacía
        """
        for prefijo, rol, nombre in (("ADMIN", "administrador", "Administrador EcoAgua"),
                                     ("OPERADOR", "operador", "Operador EcoAgua")):
            usuario = os.environ.get(f"ECOAGUA_{prefijo}_USUARIO", "").strip()
            password = os.environ.get(f"ECOAGUA_{prefijo}_PASSWORD", "")
            if not usuario or not password:
                continue
            if Usuario.query.filter_by(usuario=usuario.lower()).first():
                click.echo(f"Usuario «{usuario}» ya existe.")
                continue
            try:
                guardar_usuario_cli(usuario, nombre, rol, password)
                click.echo(f"Usuario «{usuario}» ({ROLES[rol]}) creado.")
            except ValueError as e:
                click.echo(f"No se creó «{usuario}»: {e}")
        if os.environ.get("ECOAGUA_DATOS_EJEMPLO") == "1" and Reporte.query.count() == 0:
            generar_datos_ejemplo(30)
            click.echo("30 reportes de ejemplo creados.")

    @app.cli.command("datos-ejemplo")
    @click.option("--cantidad", default=30, show_default=True)
    def datos_ejemplo(cantidad):
        """Crea reportes de ejemplo en barrios de Montería (marcados como prueba)."""
        generar_datos_ejemplo(cantidad)
        click.echo(f"{cantidad} reportes de ejemplo creados.")

    @app.cli.command("datos-prueba")
    @click.option("--cantidad", default=25, show_default=True)
    @click.option("--lat", type=float, default=None, help="Latitud central (defecto: centro del mapa).")
    @click.option("--lng", type=float, default=None, help="Longitud central.")
    def datos_prueba(cantidad, lat, lng):
        """Crea reportes de PRUEBA (marcados es_prueba=1, nombre '[PRUEBA] ...')."""
        generar_datos_prueba(cantidad, lat, lng)
        click.echo(f"{cantidad} reportes de prueba creados. Para borrarlos: flask --app backend/app borrar-datos-prueba")

    def generar_datos_prueba(cantidad, lat, lng):
        lat = lat if lat is not None else app.config["MAPA_LAT"]
        lng = lng if lng is not None else app.config["MAPA_LNG"]
        rng = random.Random()
        focos = [(lat + rng.uniform(-0.03, 0.03), lng + rng.uniform(-0.03, 0.03), f"Sector de prueba {i+1}")
                 for i in range(4)]
        admin = Usuario.query.order_by(Usuario.id).first()
        for i in range(cantidad):
            flat, flng, barrio = rng.choice(focos)
            datos = dict(
                nombre_ciudadano=f"[PRUEBA] Ciudadano {i+1}",
                correo=f"prueba{i+1}@ejemplo.invalid",
                telefono=None,
                tipo_fuga=rng.choice(list(TIPOS_FUGA)),
                descripcion="[PRUEBA] Reporte generado automáticamente para verificar el sistema.",
                latitud=round(flat + rng.gauss(0, 0.002), 6),
                longitud=round(flng + rng.gauss(0, 0.002), 6),
                origen_ubicacion="mapa",
                precision_gps_m=None,
                barrio=barrio,
                direccion_referencia=None,
            )
            fecha = ahora() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
            r = crear_reporte(datos, None, es_prueba=True, fecha=fecha)
            destino = rng.choices(list(ESTADOS), weights=[5, 3, 4])[0]
            if destino in ("en_proceso", "resuelto"):
                cambiar_estado(r, "en_proceso", admin, "[PRUEBA]")
            if destino == "resuelto":
                cambiar_estado(r, "resuelto", admin, "[PRUEBA]")

    @app.cli.command("borrar-datos-prueba")
    def borrar_datos_prueba():
        """Elimina SOLO los reportes marcados como de prueba (y su historial)."""
        reportes = Reporte.query.filter_by(es_prueba=True).all()
        for r in reportes:
            db.session.delete(r)
        db.session.flush()
        # Ciudadanos que quedaron sin reportes (los de prueba).
        for c in Ciudadano.query.filter(~Ciudadano.reportes.any()).all():
            db.session.delete(c)
        db.session.commit()
        click.echo(f"{len(reportes)} reportes de prueba eliminados.")


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
