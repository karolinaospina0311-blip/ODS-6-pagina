"""
Datos de ejemplo de EcoAgua para demostración y evaluación.

Crea reportes en barrios de Montería con distintos tipos de fuga, estados e
historial. Todos quedan marcados con es_prueba = TRUE (en el panel llevan la
etiqueta "Prueba" y se pueden ocultar o borrar con `borrar-datos-prueba`).
Los correos terminan en @ejemplo.invalid, un dominio reservado que no existe.
"""
import random
from datetime import timedelta
from io import BytesIO

from PIL import Image, ImageDraw

from models import ESTADOS, Reporte, Usuario, ahora
from servicios import cambiar_estado, crear_reporte

BARRIOS = [
    ("Centro", 8.7570, -75.8855),
    ("La Castellana", 8.7720, -75.8720),
    ("El Recreo", 8.7790, -75.8680),
    ("La Granja", 8.7380, -75.8700),
    ("Cantaclaro", 8.7310, -75.8580),
    ("Mocarí", 8.7950, -75.8600),
    ("Rancho Grande", 8.7400, -75.8960),
    ("Los Colores", 8.7510, -75.8730),
]

CIUDADANOS = [
    ("Laura Martínez", "laura.martinez@ejemplo.invalid", "300 555 0101"),
    ("Carlos Pérez", "carlos.perez@ejemplo.invalid", "301 555 0102"),
    ("Ana Sofía Díaz", "ana.diaz@ejemplo.invalid", None),
    ("Jorge Hernández", "jorge.hernandez@ejemplo.invalid", "310 555 0104"),
    ("María Fernanda Ruiz", "maria.ruiz@ejemplo.invalid", "320 555 0105"),
    ("Andrés Gómez", "andres.gomez@ejemplo.invalid", None),
    ("Valentina Torres", "valentina.torres@ejemplo.invalid", "311 555 0107"),
    ("Luis Ramírez", "luis.ramirez@ejemplo.invalid", "312 555 0108"),
    ("Camila Rodríguez", "camila.rodriguez@ejemplo.invalid", "315 555 0109"),
    ("Daniel Castro", "daniel.castro@ejemplo.invalid", None),
]

DESCRIPCIONES = {
    "tuberia_calle": ["Tubo roto en la vía, el agua corre por toda la calle desde la mañana.",
                      "Se rompió la tubería frente a la tienda y hay un charco grande."],
    "anden": ["Sale agua del andén de forma constante, ya está dañando el piso.",
              "Brota agua por una grieta del andén cerca de la esquina."],
    "medidor": ["El medidor de la casa gotea sin parar aunque todo esté cerrado.",
                "Fuga en la acometida antes del medidor, se escucha el agua."],
    "hidrante": ["El hidrante de la esquina está botando agua desde hace dos días.",
                 "Hidrante con la tapa dañada, sale un chorro pequeño."],
    "tanque_red": ["La red pública tiene una fuga cerca del parque del barrio.",
                   "Fuga en el tanque de distribución, se ve el agua bajando por la pared."],
    "otro": ["Hay agua acumulada que no es de lluvia, parece una fuga subterránea.",
             "Fuga sin identificar en el separador de la avenida."],
}

NOTAS = {
    "en_proceso": ["Cuadrilla asignada, se atenderá en las próximas 24 horas.",
                   "Equipo técnico en camino para revisar la fuga."],
    "resuelto": ["Tubería reparada y servicio normalizado.",
                 "Se cambió el tramo dañado. Gracias por reportar."],
}


def _foto_ejemplo(rng, texto):
    """Imagen sintética (claramente marcada como ejemplo) para ver el flujo con fotografía."""
    img = Image.new("RGB", (640, 420), (rng.randint(20, 50), rng.randint(90, 130), rng.randint(140, 190)))
    d = ImageDraw.Draw(img)
    for _ in range(6):
        x, y = rng.randint(0, 600), rng.randint(0, 380)
        r = rng.randint(30, 90)
        d.ellipse((x, y, x + r, y + r), fill=(rng.randint(120, 200), rng.randint(190, 230), 255))
    d.rectangle((0, 360, 640, 420), fill=(14, 59, 67))
    d.text((18, 382), f"FOTO DE EJEMPLO - {texto}", fill=(255, 255, 255))
    salida = BytesIO()
    img.save(salida, "JPEG", quality=70)
    return salida.getvalue()


def generar_datos_ejemplo(cantidad=30, semilla=2026):
    rng = random.Random(semilla)
    usuarios = Usuario.query.filter_by(activo=True).order_by(Usuario.id).all()
    creados = []
    for i in range(cantidad):
        barrio, lat, lng = rng.choice(BARRIOS)
        nombre, correo, telefono = rng.choice(CIUDADANOS)
        tipo = rng.choice(list(DESCRIPCIONES))
        gps = rng.random() < 0.6
        datos = dict(
            nombre_ciudadano=nombre,
            correo=correo,
            telefono=telefono,
            tipo_fuga=tipo,
            descripcion=rng.choice(DESCRIPCIONES[tipo]),
            latitud=round(lat + rng.gauss(0, 0.0025), 6),
            longitud=round(lng + rng.gauss(0, 0.0025), 6),
            origen_ubicacion="gps" if gps else "mapa",
            precision_gps_m=round(rng.uniform(5, 30), 1) if gps else None,
            barrio=barrio,
            direccion_referencia=f"Calle {rng.randint(1, 60)} # {rng.randint(1, 40)}-{rng.randint(1, 99)}",
        )
        fecha = ahora() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
        r = crear_reporte(datos, _foto_ejemplo(rng, barrio.upper()), es_prueba=True, fecha=fecha)
        destino = rng.choices(list(ESTADOS), weights=[5, 3, 4])[0]
        quien = rng.choice(usuarios) if usuarios else None
        if destino in ("en_proceso", "resuelto"):
            cambiar_estado(r, "en_proceso", quien, rng.choice(NOTAS["en_proceso"]))
        if destino == "resuelto":
            cambiar_estado(r, "resuelto", quien, rng.choice(NOTAS["resuelto"]))
        creados.append(r)
    return creados
