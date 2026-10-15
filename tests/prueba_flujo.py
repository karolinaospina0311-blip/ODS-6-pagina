"""Prueba automática del flujo completo de EcoAgua.
Usa una base de datos temporal: NO toca instance/ecoagua.db.
Ejecutar desde la carpeta del proyecto:  python tests/prueba_flujo.py
"""
import io, os, re, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tmp}/t.db")  # o PostgreSQL si se define
os.environ["ECOAGUA_SECRET_KEY"] = "test"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from PIL import Image
from app import app
from models import db, Usuario, Ciudadano, Reporte, HistorialEstado
app.config["TESTING"] = True
with app.app_context():
    db.drop_all(); db.create_all()  # base limpia

def img(fmt="JPEG", size=(800,600)):
    b = io.BytesIO(); Image.new("RGB", size, (20,120,200)).save(b, fmt); b.seek(0); return b

ok = lambda cond, msg: print(("✔ " if cond else "✘ FALLA: ") + msg) or (cond or sys.exit(1))
c = app.test_client()

# Página pública y archivos existentes
for p in ["/", "/styles.css", "/script.js", "/reportes.js", "/static/vendor/leaflet/leaflet.js", "/static/vendor/chartjs/chart.umd.js"]:
    ok(c.get(p).status_code == 200, f"GET {p} 200")
ok(c.get("/app.py").status_code == 404, "El código fuente del servidor no se expone")
ok(c.get("/config.py").status_code == 404, "config.py no se expone")
ok(c.get("/instance/secret_key").status_code == 404, "secret_key no se expone")
cfg = c.get("/api/config").get_json(); ok(len(cfg["tipos_fuga"]) == 6, "api/config devuelve tipos de fuga")

base = dict(nombre="Ana Pérez", correo="ana@correo.com", telefono="300 123 4567", tipo_fuga="tuberia_calle",
            descripcion="Sale agua a presión de un tubo roto", latitud="8.7479", longitud="-75.8814",
            origen_ubicacion="gps", precision_gps="12", barrio="La Granja", direccion="Calle 30")

# Validaciones
r = c.post("/api/reportes", data={}); j = r.get_json()
ok(r.status_code == 400 and {"nombre","correo","tipo_fuga","descripcion","ubicacion","foto"} <= set(j["errores"]), "Campos obligatorios validados")
r = c.post("/api/reportes", data={**base, "foto": (io.BytesIO(b"no soy imagen"), "x.jpg")})
ok(r.status_code == 400 and "foto" in r.get_json()["errores"], "Imagen falsa rechazada")
r = c.post("/api/reportes", data={**base, "foto": (io.BytesIO(b"GIF89a"+b"0"*50), "x.gif")})
ok(r.status_code == 400, "GIF rechazado")
r = c.post("/api/reportes", data={**base, "latitud": "999", "foto": (img(), "f.jpg")})
ok(r.status_code == 400 and "ubicacion" in r.get_json()["errores"], "Coordenadas fuera de rango rechazadas")
r = c.post("/api/reportes", data={**base, "correo": "malo", "foto": (img(), "f.jpg")})
ok(r.status_code == 400 and "correo" in r.get_json()["errores"], "Correo inválido rechazado")
r = c.post("/api/reportes", data={**base, "sitio_web": "spam", "foto": (img(), "f.jpg")})
ok(r.status_code == 400, "Honeypot anti-bots")
r = c.post("/api/reportes", data={**base, "nombre": "x'); DROP TABLE reportes;--", "correo": "otro@correo.com", "foto": (img(), "f.jpg")})
ok(r.status_code == 201, "Texto con SQL se guarda como texto (consultas parametrizadas)")

# Reporte válido con foto PNG (con transparencia) y EXIF
r = c.post("/api/reportes", data={**base, "foto": (img("PNG"), "fuga.png")})
j = r.get_json(); ok(r.status_code == 201 and re.fullmatch(r"ECO-\d{4}-\d{5}", j["numero_seguimiento"]), f"Reporte creado: {j.get('numero_seguimiento')}")
num = j["numero_seguimiento"]
with app.app_context():
    rep = Reporte.query.filter_by(numero_seguimiento=num).one()
    ok(rep.latitud == 8.7479 and rep.longitud == -75.8814, "Coordenadas guardadas en SQL")
    ok(rep.estado == "pendiente", "Estado inicial Pendiente")
    ok(rep.fotografia is not None and rep.fotografia.contenido[:3] == b"\xff\xd8\xff", "Foto guardada en la base de datos (JPEG)")
    ok(rep.ciudadano.correo == "ana@correo.com" and rep.nombre_ciudadano == "Ana Pérez", "Ciudadano guardado en su tabla")
    ok(len(rep.historial) == 1, "Historial inicial registrado")
    rid = rep.id
# Primer número
primero = "ECO-" + num[4:8] + "-00001"; ok(c.get("/api/reportes/" + primero).status_code == 200, primero + " existe (primer reporte)")

# Consulta pública
j = c.get(f"/api/reportes/{num.lower()}").get_json()
ok(j["ok"] and j["reporte"]["estado_texto"] == "Pendiente", "Consulta pública (acepta minúsculas) → Pendiente")
ok("correo" not in j["reporte"] and "nombre_ciudadano" not in j["reporte"] and "telefono" not in j["reporte"], "La consulta pública no expone datos personales")
ok(c.get(j["reporte"]["foto"]).status_code == 200, "Foto visible en la consulta")
ok(c.get("/api/reportes/ECO-2026-99999").status_code == 404, "Número inexistente → 404")
ok(c.get("/api/reportes/hola").status_code == 400, "Formato inválido → 400")

# Rutas admin protegidas
for p in ["/admin/", "/admin/reportes", "/admin/mapa", f"/admin/reportes/{rid}", f"/admin/fotos/{rid}"]:
    ok(c.get(p).status_code == 302, f"{p} sin sesión → redirige a login")
ok(c.get("/admin/api/mapa").status_code == 401, "API mapa sin sesión → 401")
ok(c.get("/admin/api/estadisticas").status_code == 401, "API estadísticas sin sesión → 401")
r = c.post(f"/admin/reportes/{rid}/estado", data={"estado": "resuelto"})
ok(r.status_code == 302 and "login" in r.headers["Location"], "Ciudadano no puede cambiar estados")
ok(c.get(f"/api/reportes/{num}").get_json()["reporte"]["estado"] == "pendiente", "…y el estado no cambió")
ok(c.put(f"/api/reportes/{num}").status_code == 405 and c.delete(f"/api/reportes/{num}").status_code == 405, "No hay métodos públicos para modificar/borrar")

# Mismo correo en otro reporte -> reutiliza el ciudadano (3FN, sin datos repetidos)
r = c.post("/api/reportes", data={**base, "descripcion": "Otra fuga en la misma cuadra", "foto": (img(), "f2.jpg")})
num2 = r.get_json()["numero_seguimiento"]
with app.app_context():
    ok(Ciudadano.query.filter_by(correo="ana@correo.com").count() == 1, "Correo repetido no duplica al ciudadano")
    ok(len(Ciudadano.query.filter_by(correo="ana@correo.com").one().reportes) == 2, "Ciudadano con 2 reportes")
    rid2 = Reporte.query.filter_by(numero_seguimiento=num2).one().id

# Crear usuarios por CLI
runner = app.test_cli_runner()
res = runner.invoke(args=["crear-usuario", "--usuario", "Admin", "--nombre", "Admin Uno", "--rol", "administrador", "--password", "clave-segura-123"])
ok("creado" in res.output, "CLI crear-usuario (administrador)")
res = runner.invoke(args=["crear-usuario", "--usuario", "operador", "--nombre", "Operador Uno", "--rol", "operador", "--password", "clave-operador-1"])
ok("creado" in res.output, "CLI crear-usuario (operador)")
res = runner.invoke(args=["crear-usuario", "--usuario", "x", "--nombre", "x", "--rol", "operador", "--password", "corta"])
ok(res.exit_code != 0, "Contraseña corta rechazada")

# Login
html = c.get("/admin/login").get_data(as_text=True)
csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
r = c.post("/admin/login", data={"csrf": "malo", "usuario": "admin", "password": "clave-segura-123"})
ok(r.status_code == 400, "Login sin CSRF válido rechazado")
r = c.post("/admin/login", data={"csrf": csrf, "usuario": "admin", "password": "incorrecta"})
ok("incorrectos" in r.get_data(as_text=True), "Contraseña incorrecta rechazada")
r = c.post("/admin/login?siguiente=https://malo.com", data={"csrf": csrf, "usuario": "admin", "password": "clave-segura-123"})
ok(r.status_code == 302 and r.headers["Location"].endswith("/admin/"), "Login correcto (sin redirección abierta)")

# Dashboard
h = c.get("/admin/").get_data(as_text=True); ok("Estadísticas" in h, "Panel de estadísticas carga")
h = c.get("/admin/reportes").get_data(as_text=True)
ok(num in h and "ana@correo.com" in h and "300 123 4567" in h and "8.74790" in h, "Listado muestra número, correo, teléfono, coordenadas")
ok("DROP TABLE" in h and "<script" not in h.split("DROP")[0][-50:], "Texto escapado en HTML")
ok(c.get(f"/admin/fotos/{rid}").status_code == 200, "Admin ve la foto")
h = c.get(f"/admin/reportes/{rid}").get_data(as_text=True); ok("La Granja" in h and "GPS del dispositivo" in h, "Detalle del reporte")
m = c.get("/admin/api/mapa").get_json(); ok(any(x["numero"] == num for x in m["reportes"]), "API mapa incluye el reporte")
h = c.get("/admin/reportes?q=granja").get_data(as_text=True); ok(num in h, "Búsqueda funciona")

# Cambio de estado
csrf = re.search(r'name="csrf" value="([^"]+)"', c.get("/admin/reportes").get_data(as_text=True)).group(1)
r = c.post(f"/admin/reportes/{rid}/estado", data={"estado": "en_proceso"})
ok(r.status_code == 400, "Cambio de estado sin CSRF rechazado")
r = c.post(f"/admin/reportes/{rid}/estado", data={"csrf": csrf, "estado": "inventado"}, follow_redirects=True)
ok("no válido" in r.get_data(as_text=True), "Estado inválido rechazado")
c.post(f"/admin/reportes/{rid}/estado", data={"csrf": csrf, "estado": "en_proceso", "nota": "Cuadrilla asignada"})
j = c.get(f"/api/reportes/{num}").get_json()["reporte"]
ok(j["estado_texto"] == "En proceso" and j["historial"][-1]["nota"] == "Cuadrilla asignada", "Ciudadano ve EN PROCESO + nota")
s = c.get("/admin/api/estadisticas").get_json(); ok(s["en_proceso"] == 1, "Estadísticas reflejan el cambio")
c.post(f"/admin/reportes/{rid}/estado", data={"csrf": csrf, "estado": "resuelto"})
ok(c.get(f"/api/reportes/{num}").get_json()["reporte"]["estado_texto"] == "Resuelto", "Ciudadano ve RESUELTO")
r = c.post(f"/admin/reportes/{rid}/estado", data={"csrf": csrf, "estado": "resuelto"}, follow_redirects=True)
ok("ya está en estado" in r.get_data(as_text=True), "Mismo estado no se duplica")
with app.app_context():
    ok(HistorialEstado.query.filter_by(reporte_id=rid).count() == 3, "Historial con 3 registros")
    ok(db.session.get(Reporte, rid).historial[-1].usuario.usuario == "admin", "Historial relacionado con el usuario")

s = c.get("/admin/api/estadisticas").get_json()
ok(s["total"] == 3 and s["resuelto"] == 1 and s["pendiente"] == 2, f"Totales desde SQL: {s['total']} total")
ok(s["zonas"][0]["nombre"] == "La Granja" and s["zonas"][0]["total"] == 3, "Zona agrupada por coordenadas")
ok(sum(d["total"] for d in s["evolucion"]) == 3, "Evolución diaria cuenta los reportes")

# Datos de prueba
res = runner.invoke(args=["datos-prueba", "--cantidad", "12", "--lat", "8.75", "--lng", "-75.88"])
ok("12 reportes de prueba" in res.output, "CLI datos-prueba")
ok(c.get("/admin/api/estadisticas").get_json()["total"] == 15, "Total 15 con datos de prueba")
h = c.get("/admin/reportes?prueba_enviado=1").get_data(as_text=True); ok("[PRUEBA]" not in h, "Filtro oculta datos de prueba")
res = runner.invoke(args=["borrar-datos-prueba"]); ok("12 reportes de prueba eliminados" in res.output, "CLI borrar-datos-prueba")
with app.app_context():
    ok(Ciudadano.query.filter(Ciudadano.correo.like("%@ejemplo.invalid")).count() == 0, "Ciudadanos de prueba eliminados")
ok(c.get("/admin/api/estadisticas").get_json()["total"] == 3, "Solo quedan los reportes reales")

# Gestión de usuarios (solo administrador)
h = c.get("/admin/usuarios").get_data(as_text=True); ok("Registrar usuario" in h and "operador" in h, "Admin ve la gestión de usuarios")
csrf = re.search(r'name="csrf" value="([^"]+)"', h).group(1)
r = c.post("/admin/usuarios", data={"csrf": csrf, "usuario": "nuevo.op", "nombre": "Nuevo Operador", "rol": "operador", "password": "corta"})
ok(r.status_code == 400 and "10 caracteres" in r.get_data(as_text=True), "Registro con contraseña corta rechazado")
r = c.post("/admin/usuarios", data={"csrf": csrf, "usuario": "nuevo.op", "nombre": "Nuevo Operador", "rol": "jefe", "password": "clave-larga-123"})
ok(r.status_code == 400, "Registro con rol inválido rechazado")
r = c.post("/admin/usuarios", data={"csrf": csrf, "usuario": "nuevo.op", "nombre": "Nuevo Operador", "rol": "operador", "password": "clave-larga-123"}, follow_redirects=True)
ok("creado" in r.get_data(as_text=True), "Admin registra un usuario")
r = c.post("/admin/usuarios", data={"csrf": csrf, "usuario": "nuevo.op", "nombre": "Repetido", "rol": "operador", "password": "clave-larga-123"})
ok(r.status_code == 400, "Usuario repetido rechazado")
with app.app_context():
    uid = Usuario.query.filter_by(usuario="nuevo.op").one().id
    yo = Usuario.query.filter_by(usuario="admin").one().id
r = c.post(f"/admin/usuarios/{yo}/activo", data={"csrf": csrf}, follow_redirects=True)
ok("propia cuenta" in r.get_data(as_text=True), "No puede desactivarse a sí mismo")
c.post(f"/admin/usuarios/{uid}/activo", data={"csrf": csrf})
with app.app_context():
    ok(db.session.get(Usuario, uid).activo is False, "Admin desactiva un usuario")

# Logout
c.post("/admin/logout", data={"csrf": csrf})
ok(c.get("/admin/reportes").status_code == 302, "Tras cerrar sesión, el panel vuelve a estar protegido")

# Usuario regular (operador)
html = c.get("/admin/login").get_data(as_text=True)
csrf = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
r = c.post("/admin/login", data={"csrf": csrf, "usuario": "nuevo.op", "password": "clave-larga-123"})
ok("incorrectos" in r.get_data(as_text=True), "Usuario desactivado no puede ingresar")
r = c.post("/admin/login", data={"csrf": csrf, "usuario": "operador", "password": "clave-operador-1"})
ok(r.status_code == 302, "Operador inicia sesión")
h = c.get("/admin/reportes").get_data(as_text=True)
ok(num in h and "/admin/usuarios" not in h, "Operador gestiona reportes y no ve el menú Usuarios")
ok(c.get("/admin/usuarios").status_code == 403, "Operador no puede entrar a gestión de usuarios")
csrf = re.search(r'name="csrf" value="([^"]+)"', h).group(1)
c.post(f"/admin/reportes/{rid2}/estado", data={"csrf": csrf, "estado": "en_proceso"})
ok(c.get(f"/api/reportes/{num2}").get_json()["reporte"]["estado"] == "en_proceso", "Operador cambia estados")
c.post("/admin/logout", data={"csrf": csrf})

# Comando sembrar (usuarios de prueba y datos de ejemplo desde variables de entorno)
os.environ.update(ECOAGUA_ADMIN_USUARIO="demo.admin", ECOAGUA_ADMIN_PASSWORD="demo-admin-2026",
                  ECOAGUA_OPERADOR_USUARIO="demo.operador", ECOAGUA_OPERADOR_PASSWORD="demo-operador-2026")
res = runner.invoke(args=["sembrar"]); ok("demo.admin" in res.output and "demo.operador" in res.output, "CLI sembrar crea usuarios de prueba")
res = runner.invoke(args=["sembrar"]); ok("ya existe" in res.output, "CLI sembrar no duplica usuarios")
print("\nTODAS LAS PRUEBAS PASARON")
