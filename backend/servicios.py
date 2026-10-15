"""
Lógica de negocio de EcoAgua: validación de formularios, fotografías,
números de seguimiento, cambios de estado y estadísticas.
"""
import math
import os
import re
import threading
import time
import uuid
from io import BytesIO
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func

from models import ESTADOS, TIPOS_FUGA, Ciudadano, Fotografia, HistorialEstado, Reporte, ahora, db

ZONA_LOCAL = ZoneInfo(os.environ.get("ECOAGUA_ZONA_HORARIA", "America/Bogota"))

RE_SEGUIMIENTO = re.compile(r"^ECO-\d{4}-\d{5,7}$")
RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
RE_TELEFONO = re.compile(r"^[0-9+()\-\s]{7,20}$")

FORMATOS_FOTO = {"JPEG", "PNG", "WEBP"}
EXTENSIONES_FOTO = {".jpg", ".jpeg", ".png", ".webp"}
LADO_MAXIMO_FOTO = 2000

# Imágenes con más píxeles que esto se rechazan (protege contra "bombas" de descompresión).
Image.MAX_IMAGE_PIXELS = 50_000_000


class ErrorValidacion(Exception):
    def __init__(self, errores):
        super().__init__("Datos no válidos")
        self.errores = errores  # dict campo -> mensaje


# ---------------------------------------------------------------- fechas

def a_hora_local(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(ZONA_LOCAL)


def formatear_fecha(dt, con_hora=True):
    local = a_hora_local(dt)
    if local is None:
        return ""
    return local.strftime("%d/%m/%Y %I:%M %p" if con_hora else "%d/%m/%Y")


# ---------------------------------------------------------------- validación

def _texto(form, campo, maximo):
    valor = (form.get(campo) or "").strip()
    valor = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", valor)
    return valor[:maximo] if len(valor) > maximo else valor, len(valor) > maximo


def validar_formulario_reporte(form, foto, foto_obligatoria):
    """Devuelve un dict con datos limpios o lanza ErrorValidacion."""
    errores = {}
    datos = {}

    nombre, largo = _texto(form, "nombre", 120)
    if len(nombre) < 3:
        errores["nombre"] = "Escribe tu nombre completo."
    elif largo:
        errores["nombre"] = "El nombre es demasiado largo (máximo 120 caracteres)."
    datos["nombre_ciudadano"] = nombre

    correo, largo = _texto(form, "correo", 254)
    if not RE_CORREO.match(correo) or largo:
        errores["correo"] = "Escribe un correo electrónico válido, por ejemplo nombre@correo.com."
    datos["correo"] = correo.lower()

    telefono, _ = _texto(form, "telefono", 30)
    if telefono and not RE_TELEFONO.match(telefono):
        errores["telefono"] = "El teléfono solo puede tener números, espacios y los signos + ( ) -."
    datos["telefono"] = telefono or None

    tipo = (form.get("tipo_fuga") or "").strip()
    if tipo not in TIPOS_FUGA:
        errores["tipo_fuga"] = "Elige el tipo de fuga."
    datos["tipo_fuga"] = tipo

    descripcion, largo = _texto(form, "descripcion", 2000)
    if len(descripcion) < 10:
        errores["descripcion"] = "Describe la fuga con al menos 10 caracteres."
    elif largo:
        errores["descripcion"] = "La descripción es demasiado larga (máximo 2000 caracteres)."
    datos["descripcion"] = descripcion

    barrio, _ = _texto(form, "barrio", 120)
    datos["barrio"] = barrio or None
    direccion, _ = _texto(form, "direccion", 255)
    datos["direccion_referencia"] = direccion or None

    try:
        lat = float(form.get("latitud", ""))
        lng = float(form.get("longitud", ""))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
            raise ValueError
        datos["latitud"] = round(lat, 7)
        datos["longitud"] = round(lng, 7)
    except (TypeError, ValueError):
        errores["ubicacion"] = "Marca la ubicación de la fuga con el GPS o tocando el mapa."

    origen = form.get("origen_ubicacion", "mapa")
    datos["origen_ubicacion"] = origen if origen in ("gps", "mapa") else "mapa"
    try:
        precision = float(form.get("precision_gps", ""))
        datos["precision_gps_m"] = round(precision, 1) if 0 < precision < 100000 else None
    except (TypeError, ValueError):
        datos["precision_gps_m"] = None

    tiene_foto = foto is not None and foto.filename
    if not tiene_foto and foto_obligatoria:
        errores["foto"] = "Adjunta una fotografía de la fuga."

    if errores:
        raise ErrorValidacion(errores)
    return datos


def normalizar_seguimiento(valor):
    valor = (valor or "").strip().upper().replace(" ", "")
    return valor if RE_SEGUIMIENTO.match(valor) else None


# ---------------------------------------------------------------- fotografías

def procesar_foto(archivo, max_mb):
    """Valida la imagen con Pillow, la re-codifica como JPEG (elimina metadatos EXIF,
    incluida la ubicación del teléfono) y devuelve los bytes listos para guardar en la BD."""
    ext = os.path.splitext(archivo.filename or "")[1].lower()
    if ext and ext not in EXTENSIONES_FOTO:
        raise ErrorValidacion({"foto": "La fotografía debe ser JPG, PNG o WEBP."})

    datos = archivo.read(int(max_mb * 1024 * 1024) + 1)
    if len(datos) > max_mb * 1024 * 1024:
        raise ErrorValidacion({"foto": f"La fotografía supera el tamaño máximo de {max_mb:g} MB."})
    if not datos:
        raise ErrorValidacion({"foto": "La fotografía está vacía."})

    try:
        with Image.open(BytesIO(datos)) as prueba:
            if prueba.format not in FORMATOS_FOTO:
                raise ErrorValidacion({"foto": "La fotografía debe ser JPG, PNG o WEBP."})
            prueba.verify()
        with Image.open(BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                fondo = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                fondo.paste(rgba, mask=rgba.split()[-1])
                img = fondo
            else:
                img = img.convert("RGB")
            img.thumbnail((LADO_MAXIMO_FOTO, LADO_MAXIMO_FOTO))
            salida = BytesIO()
            img.save(salida, "JPEG", quality=82, optimize=True)
            return salida.getvalue()
    except ErrorValidacion:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise ErrorValidacion({"foto": "El archivo no es una imagen válida o está dañado."})


# ---------------------------------------------------------------- reportes

def obtener_o_crear_ciudadano(nombre, correo, telefono):
    """Un ciudadano se identifica por su correo; si ya existe se actualizan sus datos de contacto."""
    ciudadano = Ciudadano.query.filter_by(correo=correo).first()
    if ciudadano is None:
        ciudadano = Ciudadano(correo=correo, nombre=nombre, telefono=telefono)
        db.session.add(ciudadano)
    else:
        ciudadano.nombre = nombre
        if telefono:
            ciudadano.telefono = telefono
    return ciudadano


def crear_reporte(datos, foto_bytes=None, es_prueba=False, fecha=None):
    """Inserta el reporte y le asigna el número ECO-AAAA-NNNNN a partir de su id."""
    datos = dict(datos)
    ciudadano = obtener_o_crear_ciudadano(
        datos.pop("nombre_ciudadano"), datos.pop("correo"), datos.pop("telefono", None)
    )
    reporte = Reporte(
        numero_seguimiento=f"TMP-{uuid.uuid4().hex[:14]}",
        ciudadano=ciudadano,
        estado="pendiente",
        es_prueba=es_prueba,
        **datos,
    )
    if fecha is not None:
        reporte.fecha_creacion = fecha
        reporte.fecha_actualizacion = fecha
    if foto_bytes:
        reporte.fotografia = Fotografia(
            contenido=foto_bytes, tamano_bytes=len(foto_bytes), tipo_mime="image/jpeg"
        )
    db.session.add(reporte)
    db.session.flush()  # obtiene el id sin cerrar la transacción
    anio = a_hora_local(reporte.fecha_creacion or ahora()).year
    reporte.numero_seguimiento = f"ECO-{anio}-{reporte.id:05d}"
    db.session.add(
        HistorialEstado(
            reporte=reporte, estado_anterior=None, estado_nuevo="pendiente",
            nota="Reporte recibido.", fecha=reporte.fecha_creacion,
        )
    )
    db.session.commit()
    return reporte


def contenido_foto(reporte):
    """Bytes de la fotografía de un reporte, o None si no tiene."""
    if reporte is None or reporte.fotografia is None:
        return None
    return reporte.fotografia.contenido


def cambiar_estado(reporte, nuevo_estado, usuario, nota=None):
    if nuevo_estado not in ESTADOS:
        raise ErrorValidacion({"estado": "Estado no válido."})
    if nuevo_estado == reporte.estado:
        raise ErrorValidacion({"estado": f"El reporte ya está en estado «{ESTADOS[nuevo_estado]}»."})
    nota = (nota or "").strip()[:500] or None
    anterior = reporte.estado
    reporte.estado = nuevo_estado
    reporte.fecha_actualizacion = ahora()
    db.session.add(
        HistorialEstado(
            reporte=reporte, usuario=usuario,
            estado_anterior=anterior, estado_nuevo=nuevo_estado, nota=nota,
        )
    )
    db.session.commit()


def reporte_publico(reporte, url_foto):
    """Datos que puede ver cualquier persona con el número de seguimiento.
    No incluye nombre, correo ni teléfono del ciudadano."""
    return {
        "numero_seguimiento": reporte.numero_seguimiento,
        "fecha": formatear_fecha(reporte.fecha_creacion),
        "fecha_actualizacion": formatear_fecha(reporte.fecha_actualizacion),
        "tipo_fuga": reporte.tipo_fuga_texto,
        "descripcion": reporte.descripcion,
        "latitud": reporte.latitud,
        "longitud": reporte.longitud,
        "barrio": reporte.barrio,
        "direccion": reporte.direccion_referencia,
        "estado": reporte.estado,
        "estado_texto": reporte.estado_texto,
        "foto": url_foto,
        "historial": [
            {
                "estado": h.estado_nuevo,
                "estado_texto": h.estado_nuevo_texto,
                "fecha": formatear_fecha(h.fecha),
                "nota": h.nota,
            }
            for h in reporte.historial
        ],
    }


# ---------------------------------------------------------------- estadísticas

RADIO_ZONA_M = 700  # dos reportes a menos de esta distancia del centro de una zona quedan juntos
_CELDA = 0.01        # índice espacial auxiliar (≈1,1 km)


def _distancia_m(lat1, lng1, lat2, lng2):
    # Aproximación equirectangular: suficiente para distancias de pocos kilómetros.
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371000 * math.hypot(x, y)


def _celda(lat, lng):
    return (math.floor(lat / _CELDA), math.floor(lng / _CELDA))


def calcular_zonas(filas, limite=10, radio_m=RADIO_ZONA_M):
    """Agrupa los reportes en zonas según la cercanía de sus coordenadas GPS.

    filas: iterable de (latitud, longitud, barrio, estado).
    Cada reporte se une a la zona existente más cercana si su centro está a menos
    de `radio_m`; si no, abre una zona nueva. El centro de la zona es el promedio
    de sus reportes. Un índice por celdas evita comparar contra todas las zonas.
    """
    zonas = []
    indice = defaultdict(list)  # celda -> posiciones en `zonas`

    for lat, lng, barrio, estado in sorted(filas, key=lambda f: (f[0], f[1])):
        cx, cy = _celda(lat, lng)
        mejor, mejor_d = None, radio_m
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in indice.get((cx + dx, cy + dy), ()):
                    z = zonas[i]
                    d = _distancia_m(lat, lng, z["lat"], z["lng"])
                    if d < mejor_d:
                        mejor, mejor_d = i, d
        if mejor is None:
            zonas.append({"lat": lat, "lng": lng, "n": 0, "barrios": Counter(),
                          "formas": {}, "estados": Counter(), "celda": (cx, cy)})
            mejor = len(zonas) - 1
            indice[(cx, cy)].append(mejor)
        z = zonas[mejor]
        z["n"] += 1
        z["lat"] += (lat - z["lat"]) / z["n"]
        z["lng"] += (lng - z["lng"]) / z["n"]
        nueva_celda = _celda(z["lat"], z["lng"])
        if nueva_celda != z["celda"]:
            indice[z["celda"]].remove(mejor)
            indice[nueva_celda].append(mejor)
            z["celda"] = nueva_celda
        z["estados"][estado] += 1
        if barrio:
            limpio = " ".join(barrio.split())
            clave = limpio.casefold()
            z["barrios"][clave] += 1
            z["formas"].setdefault(clave, limpio)

    resultado = []
    for z in zonas:
        if z["barrios"]:
            nombre = z["formas"][z["barrios"].most_common(1)[0][0]]
        else:
            nombre = f'Zona {z["lat"]:.3f}, {z["lng"]:.3f}'
        resultado.append({
            "nombre": nombre,
            "latitud": round(z["lat"], 6),
            "longitud": round(z["lng"], 6),
            "total": z["n"],
            "pendiente": z["estados"].get("pendiente", 0),
            "en_proceso": z["estados"].get("en_proceso", 0),
            "resuelto": z["estados"].get("resuelto", 0),
        })
    resultado.sort(key=lambda z: (-z["total"], -z["pendiente"]))
    resultado = resultado[:limite]
    # Si dos zonas comparten nombre de barrio se diferencian por coordenadas.
    repetidos = Counter(z["nombre"] for z in resultado)
    for z in resultado:
        if repetidos[z["nombre"]] > 1:
            z["nombre"] = f'{z["nombre"]} ({z["latitud"]:.3f}, {z["longitud"]:.3f})'
    return resultado


def obtener_estadisticas(dias=30):
    total = db.session.query(func.count(Reporte.id)).scalar() or 0
    por_estado = dict(
        db.session.query(Reporte.estado, func.count(Reporte.id)).group_by(Reporte.estado).all()
    )

    filas = db.session.query(
        Reporte.latitud, Reporte.longitud, Reporte.barrio, Reporte.estado
    ).all()
    zonas = calcular_zonas(filas)

    por_tipo = dict(
        db.session.query(Reporte.tipo_fuga, func.count(Reporte.id)).group_by(Reporte.tipo_fuga).all()
    )

    # Evolución diaria (en hora local) de los últimos `dias` días.
    hoy = datetime.now(ZONA_LOCAL).date()
    inicio = hoy - timedelta(days=dias - 1)
    desde_utc = (
        datetime.combine(inicio, datetime.min.time(), ZONA_LOCAL)
        .astimezone(timezone.utc).replace(tzinfo=None)
    )
    conteo_dias = Counter()
    for (fecha,) in db.session.query(Reporte.fecha_creacion).filter(Reporte.fecha_creacion >= desde_utc):
        conteo_dias[a_hora_local(fecha).date()] += 1
    evolucion = [
        {"fecha": (inicio + timedelta(days=i)).strftime("%d/%m"),
         "total": conteo_dias.get(inicio + timedelta(days=i), 0)}
        for i in range(dias)
    ]

    return {
        "total": total,
        "pendiente": por_estado.get("pendiente", 0),
        "en_proceso": por_estado.get("en_proceso", 0),
        "resuelto": por_estado.get("resuelto", 0),
        "zonas": zonas,
        "por_tipo": [
            {"tipo": TIPOS_FUGA.get(k, k), "total": v}
            for k, v in sorted(por_tipo.items(), key=lambda kv: -kv[1])
        ],
        "evolucion": evolucion,
        "dias": dias,
    }


# ---------------------------------------------------------------- límites de uso

class LimitadorSimple:
    """Limita peticiones por IP en memoria. Suficiente para un único proceso;
    con varios procesos/servidores conviene usar Redis (ver README)."""

    def __init__(self, maximo, ventana_segundos):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._marcas = defaultdict(list)
        self._lock = threading.Lock()

    def permitido(self, clave):
        ahora_ts = time.monotonic()
        with self._lock:
            marcas = [t for t in self._marcas[clave] if ahora_ts - t < self.ventana]
            if len(marcas) >= self.maximo:
                self._marcas[clave] = marcas
                return False
            marcas.append(ahora_ts)
            self._marcas[clave] = marcas
            return True

    def reiniciar(self, clave):
        with self._lock:
            self._marcas.pop(clave, None)
