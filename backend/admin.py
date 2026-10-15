"""
Panel administrativo de EcoAgua.

Todas las rutas bajo /admin exigen sesión, excepto el login.
Roles:
  operador       Consulta estadísticas, gestiona reportes (cambia estados) y ve el mapa.
  administrador  Todo lo anterior y además gestiona los usuarios del panel.
Los formularios que modifican datos exigen token CSRF.
"""
import hmac
import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
    request, send_file, session, url_for,
)
from sqlalchemy import or_

from io import BytesIO

from models import ESTADOS, ROLES, TIPOS_FUGA, Ciudadano, Reporte, Usuario, db
from servicios import (
    ErrorValidacion, LimitadorSimple, cambiar_estado, contenido_foto, formatear_fecha,
    obtener_estadisticas,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

limite_login = LimitadorSimple(maximo=5, ventana_segundos=300)
POR_PAGINA = 20


# ---------------------------------------------------------------- utilidades

def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def verificar_csrf():
    enviado = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
    if not hmac.compare_digest(enviado, session.get("csrf", "")):
        abort(400, description="La sesión expiró. Recarga la página e intenta de nuevo.")


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario_id = session.get("usuario_id")
        usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
        if not usuario or not usuario.activo:
            session.pop("usuario_id", None)
            if request.path.startswith("/admin/api/"):
                return jsonify(ok=False, error="Sesión requerida"), 401
            return redirect(url_for("admin.login", siguiente=request.full_path))
        g.usuario = usuario
        return vista(*args, **kwargs)
    return envoltura


def solo_administrador(vista):
    """Debe ir DESPUÉS de @login_requerido."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not g.usuario.es_administrador:
            abort(403)
        return vista(*args, **kwargs)
    return envoltura


@admin_bp.app_context_processor
def contexto_plantillas():
    return {
        "csrf_token": token_csrf,
        "ESTADOS": ESTADOS,
        "TIPOS_FUGA": TIPOS_FUGA,
        "ROLES": ROLES,
        "fmt_fecha": formatear_fecha,
    }


@admin_bp.after_request
def sin_cache(resp):
    # Evita que el navegador muestre páginas del panel desde caché tras cerrar sesión.
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _destino_seguro(url):
    if not url:
        return None
    partes = urlparse(url)
    if partes.scheme or partes.netloc or not url.startswith("/admin"):
        return None
    return url


# ---------------------------------------------------------------- sesión

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        verificar_csrf()
        ip = request.remote_addr or "?"
        if not limite_login.permitido(ip):
            flash("Demasiados intentos fallidos. Espera 5 minutos.", "error")
            return render_template("admin/login.html"), 429
        usuario = (request.form.get("usuario") or "").strip().lower()
        password = request.form.get("password") or ""
        cuenta = Usuario.query.filter_by(usuario=usuario, activo=True).first()
        if cuenta and cuenta.verificar_password(password):
            limite_login.reiniciar(ip)
            session.clear()
            session["usuario_id"] = cuenta.id
            session.permanent = False
            token_csrf()
            return redirect(_destino_seguro(request.args.get("siguiente")) or url_for("admin.panel"))
        flash("Usuario o contraseña incorrectos.", "error")
    return render_template("admin/login.html")


@admin_bp.post("/logout")
def logout():
    verificar_csrf()
    session.clear()
    return redirect(url_for("admin.login"))


# ---------------------------------------------------------------- estadísticas (inicio)

@admin_bp.get("/")
@login_requerido
def panel():
    return render_template("admin/estadisticas.html", activo="estadisticas",
                           stats=obtener_estadisticas())


@admin_bp.get("/api/estadisticas")
@login_requerido
def api_estadisticas():
    return jsonify(obtener_estadisticas())


# ---------------------------------------------------------------- gestión de reportes

@admin_bp.get("/reportes")
@login_requerido
def reportes():
    estado = request.args.get("estado", "")
    q = (request.args.get("q") or "").strip()[:100]
    # Sin filtro enviado se muestran todos; si el formulario se envió sin marcar la casilla, se ocultan.
    defecto = "0" if "prueba_enviado" in request.args else "1"
    ver_prueba = request.args.get("prueba", defecto) == "1"
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
    except ValueError:
        pagina = 1

    consulta = Reporte.query.join(Reporte.ciudadano)
    if estado in ESTADOS:
        consulta = consulta.filter(Reporte.estado == estado)
    if not ver_prueba:
        consulta = consulta.filter(Reporte.es_prueba.is_(False))
    if q:
        patron = f"%{q}%"  # SQLAlchemy envía el valor como parámetro (sin concatenar SQL)
        consulta = consulta.filter(or_(
            Reporte.numero_seguimiento.ilike(patron),
            Ciudadano.nombre.ilike(patron),
            Ciudadano.correo.ilike(patron),
            Reporte.barrio.ilike(patron),
            Reporte.descripcion.ilike(patron),
        ))
    paginacion = consulta.order_by(Reporte.fecha_creacion.desc()).paginate(
        page=pagina, per_page=POR_PAGINA, error_out=False)

    return render_template("admin/reportes.html", activo="reportes", paginacion=paginacion,
                           filtro_estado=estado, q=q, ver_prueba=ver_prueba)


@admin_bp.get("/reportes/<int:reporte_id>")
@login_requerido
def reporte_detalle(reporte_id):
    reporte = db.session.get(Reporte, reporte_id) or abort(404)
    return render_template("admin/reporte_detalle.html", activo="reportes", r=reporte)


@admin_bp.post("/reportes/<int:reporte_id>/estado")
@login_requerido
def reporte_cambiar_estado(reporte_id):
    verificar_csrf()
    reporte = db.session.get(Reporte, reporte_id) or abort(404)
    try:
        cambiar_estado(reporte, request.form.get("estado", ""), g.usuario, request.form.get("nota"))
        flash(f"Estado de {reporte.numero_seguimiento} actualizado a «{reporte.estado_texto}».", "ok")
    except ErrorValidacion as e:
        flash(next(iter(e.errores.values())), "error")
    volver = _destino_seguro(request.form.get("volver"))
    return redirect(volver or url_for("admin.reporte_detalle", reporte_id=reporte.id))


@admin_bp.get("/fotos/<int:reporte_id>")
@login_requerido
def foto(reporte_id):
    reporte = db.session.get(Reporte, reporte_id) or abort(404)
    contenido = contenido_foto(reporte)
    if not contenido:
        abort(404)
    return send_file(BytesIO(contenido), mimetype="image/jpeg")


# ---------------------------------------------------------------- mapa

@admin_bp.get("/mapa")
@login_requerido
def mapa():
    return render_template("admin/mapa.html", activo="mapa")


@admin_bp.get("/api/mapa")
@login_requerido
def api_mapa():
    estado = request.args.get("estado", "")
    consulta = Reporte.query
    if estado in ESTADOS:
        consulta = consulta.filter(Reporte.estado == estado)
    datos = [
        {
            "id": r.id,
            "numero": r.numero_seguimiento,
            "estado": r.estado,
            "estado_texto": r.estado_texto,
            "fecha": formatear_fecha(r.fecha_creacion),
            "descripcion": r.descripcion[:220],
            "tipo": r.tipo_fuga_texto,
            "barrio": r.barrio,
            "lat": r.latitud,
            "lng": r.longitud,
            "foto": url_for("admin.foto", reporte_id=r.id) if r.fotografia else None,
            "url": url_for("admin.reporte_detalle", reporte_id=r.id),
            "prueba": r.es_prueba,
        }
        for r in consulta.order_by(Reporte.fecha_creacion.desc()).all()
    ]
    return jsonify(
        reportes=datos,
        zonas=obtener_estadisticas()["zonas"],
        centro={"lat": current_app.config["MAPA_LAT"], "lng": current_app.config["MAPA_LNG"],
                "zoom": current_app.config["MAPA_ZOOM"]},
    )


# ---------------------------------------------------------------- usuarios (solo administrador)

@admin_bp.get("/usuarios")
@login_requerido
@solo_administrador
def usuarios():
    lista = Usuario.query.order_by(Usuario.rol, Usuario.usuario).all()
    return render_template("admin/usuarios.html", activo="usuarios", usuarios=lista, datos={})


@admin_bp.post("/usuarios")
@login_requerido
@solo_administrador
def usuario_crear():
    verificar_csrf()
    usuario = (request.form.get("usuario") or "").strip().lower()
    nombre = (request.form.get("nombre") or "").strip()
    rol = request.form.get("rol", "")
    password = request.form.get("password") or ""
    errores = []
    if not usuario or len(usuario) > 60 or not usuario.replace(".", "").replace("_", "").replace("-", "").isalnum():
        errores.append("El usuario solo puede tener letras, números, punto, guion y guion bajo (máximo 60).")
    if len(nombre) < 3 or len(nombre) > 120:
        errores.append("Escribe el nombre completo (entre 3 y 120 caracteres).")
    if rol not in ROLES:
        errores.append("Elige un rol válido.")
    if len(password) < 10:
        errores.append("La contraseña debe tener al menos 10 caracteres.")
    if usuario and Usuario.query.filter_by(usuario=usuario).first():
        errores.append(f"Ya existe un usuario «{usuario}».")
    if errores:
        for e in errores:
            flash(e, "error")
        lista = Usuario.query.order_by(Usuario.rol, Usuario.usuario).all()
        datos = {"usuario": usuario, "nombre": nombre, "rol": rol}
        return render_template("admin/usuarios.html", activo="usuarios", usuarios=lista, datos=datos), 400
    nuevo = Usuario(usuario=usuario, nombre=nombre, rol=rol)
    nuevo.fijar_password(password)
    db.session.add(nuevo)
    db.session.commit()
    flash(f"Usuario «{usuario}» creado con rol {ROLES[rol]}.", "ok")
    return redirect(url_for("admin.usuarios"))


@admin_bp.post("/usuarios/<int:usuario_id>/activo")
@login_requerido
@solo_administrador
def usuario_cambiar_activo(usuario_id):
    verificar_csrf()
    cuenta = db.session.get(Usuario, usuario_id) or abort(404)
    if cuenta.id == g.usuario.id:
        flash("No puedes desactivar tu propia cuenta.", "error")
        return redirect(url_for("admin.usuarios"))
    cuenta.activo = not cuenta.activo
    db.session.commit()
    flash(f"Usuario «{cuenta.usuario}» {'activado' if cuenta.activo else 'desactivado'}.", "ok")
    return redirect(url_for("admin.usuarios"))
