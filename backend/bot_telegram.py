"""
EcoAgua · Bot de Telegram para reporte y consulta de fugas de agua.

Permite a los ciudadanos:
  1. Reportar fugas paso a paso enviando nombre, correo, teléfono, tipo de fuga,
     descripción, ubicación GPS nativa y fotografía.
  2. Consultar el estado de cualquier reporte mediante su número de seguimiento
     (ej. ECO-2026-00001).
  3. Recibir ayuda e información del ODS 6.

Se ejecuta con:
  flask --app backend/app bot-telegram
o directamente:
  python backend/bot_telegram.py
"""

import asyncio
import io
import logging
import os
import re
import socket
import sys

# Forzar resolución IPv4 para evitar handshake timeouts en conexiones con IPv6 no enrutado
_orig_getaddrinfo = socket.getaddrinfo
def _getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    if family == 0 or family == socket.AF_UNSPEC:
        family = socket.AF_INET
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _getaddrinfo_ipv4

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

# Ajuste de ruta para poder importar módulos del backend
_DIR_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _DIR_BACKEND not in sys.path:
    sys.path.insert(0, _DIR_BACKEND)

from models import ESTADOS, TIPOS_FUGA, Reporte, db
from servicios import (
    ErrorValidacion,
    crear_reporte,
    formatear_fecha,
    normalizar_seguimiento,
    procesar_foto,
    RE_CORREO,
    RE_TELEFONO,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger("ecoagua_bot")

# Estados de la conversación de reporte
(
    PASO_NOMBRE,
    PASO_CORREO,
    PASO_TELEFONO,
    PASO_TIPO_FUGA,
    PASO_DESCRIPCION,
    PASO_UBICACION,
    PASO_FOTO,
    PASO_CONFIRMACION,
    PASO_CONSULTA,
) = range(9)

EMOJIS_ESTADO = {
    "pendiente": "🟡",
    "en_proceso": "🔵",
    "resuelto": "🟢",
}


def _obtener_token():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        from config import RAIZ_DIR
        ruta_env = os.path.join(RAIZ_DIR, ".env")
        if os.path.isfile(ruta_env):
            with open(ruta_env, encoding="utf-8-sig") as f:
                for linea in f:
                    linea = linea.strip()
                    if linea.startswith("TELEGRAM_BOT_TOKEN="):
                        token = linea.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    return token


async def enviar_con_reintentos(objeto_mensaje, texto, **kwargs):
    """Envía un mensaje con reintentos para soportar pequeñas demoras de red."""
    for intento in range(3):
        try:
            if hasattr(objeto_mensaje, "reply_text"):
                return await objeto_mensaje.reply_text(texto, **kwargs)
            elif hasattr(objeto_mensaje, "message") and hasattr(objeto_mensaje.message, "reply_text"):
                return await objeto_mensaje.message.reply_text(texto, **kwargs)
        except Exception as e:
            if intento == 2:
                logger.error(f"Error al enviar mensaje tras 3 intentos: {e}")
                raise
            await asyncio.sleep(1.0)


async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y opciones principales."""
    usuario = update.effective_user.first_name or "Ciudadano"
    texto = (
        f"💧 *¡Hola, {usuario}! Bienvenido a EcoAgua* 💧\n\n"
        f"Somos la plataforma ciudadana para el cuidado del agua en articulación con el "
        f"*ODS 6: Agua limpia y saneamiento*.\n\n"
        f"¿En qué te podemos ayudar hoy?\n\n"
        f"🔹 */reportar* - Reportar una fuga de agua en la vía pública.\n"
        f"🔹 */consultar* - Consultar el estado de un reporte existente.\n"
        f"🔹 */ayuda* - Información sobre el uso del bot y preguntas frecuentes.\n"
        f"🔹 */cancelar* - Cancelar cualquier trámite en curso."
    )

    teclado = [
        [
            InlineKeyboardButton("📝 Reportar fuga", callback_data="btn_iniciar_reporte"),
            InlineKeyboardButton("🔍 Consultar estado", callback_data="btn_iniciar_consulta"),
        ],
        [
            InlineKeyboardButton("ℹ️ ¿Qué es el ODS 6?", callback_data="btn_info_ods6"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(teclado)

    if update.callback_query:
        await update.callback_query.answer()
        await enviar_con_reintentos(
            update.callback_query.message, texto, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )
    else:
        await enviar_con_reintentos(
            update.message, texto, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup
        )


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información de ayuda al ciudadano."""
    texto = (
        "ℹ️ *Guía de EcoAgua*\n\n"
        "1. *¿Cómo reportar una fuga?*\n"
        "Escribe */reportar*. El bot te pedirá:\n"
        "  • Tus datos de contacto (nombre y correo).\n"
        "  • El tipo de fuga y una descripción.\n"
        "  • Tu ubicación GPS exacta (enviada desde Telegram).\n"
        "  • Una fotografía de la fuga.\n\n"
        "2. *¿Cómo consultar el estado de una fuga?*\n"
        "Escribe */consultar* seguido de tu código (ejemplo: `/consultar ECO-2026-00001`) "
        "o escribe solo */consultar* y el bot te pedirá el código.\n\n"
        "3. *¿Por qué es importante?*\n"
        "Cada fuga atendida a tiempo ahorra miles de litros de agua potable y contribuye a la meta 6.4 de los Objetivos de Desarrollo Sostenible."
    )
    await enviar_con_reintentos(update.effective_message, texto, parse_mode=ParseMode.MARKDOWN)


async def comando_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación actual y limpia el estado."""
    context.user_data.clear()
    await enviar_con_reintentos(
        update.effective_message,
        "❌ Operación cancelada. Si necesitas algo más, escribe */reportar* o */consultar*.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ==============================================================================
# FLUJO DE REPORTE DE FUGA
# ==============================================================================

async def iniciar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el asistente para registrar un reporte."""
    context.user_data.clear()
    context.user_data["reporte"] = {}

    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message

    nombre_sugerido = update.effective_user.full_name or ""
    context.user_data["reporte"]["nombre_sugerido"] = nombre_sugerido

    teclado = None
    if nombre_sugerido and len(nombre_sugerido) >= 3:
        teclado = ReplyKeyboardMarkup(
            [[KeyboardButton(f"Usar mi nombre: {nombre_sugerido}")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

    await enviar_con_reintentos(
        msg,
        "📝 *Paso 1 de 7: Tu nombre completo*\n\n"
        "Por favor, escribe tu nombre y apellidos (mínimo 3 caracteres):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=teclado if teclado else ReplyKeyboardRemove(),
    )
    return PASO_NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    nombre_sugerido = context.user_data.get("reporte", {}).get("nombre_sugerido", "")

    if texto.startswith("Usar mi nombre:") and nombre_sugerido:
        nombre = nombre_sugerido
    else:
        nombre = texto

    if len(nombre) < 3 or len(nombre) > 120:
        await enviar_con_reintentos(
            update.message,
            "⚠️ Por favor, ingresa un nombre válido (entre 3 y 120 caracteres):"
        )
        return PASO_NOMBRE

    context.user_data["reporte"]["nombre_ciudadano"] = nombre
    logger.info(f"Reporte en progreso - Nombre: {nombre}")

    await enviar_con_reintentos(
        update.message,
        f"¡Gracias, *{nombre}*!\n\n"
        "📧 *Paso 2 de 7: Tu correo electrónico*\n\n"
        "Escribe tu correo (lo usaremos para asociar tus reportes y notificarte avances):",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return PASO_CORREO


async def recibir_correo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correo = update.message.text.strip().lower()

    if not RE_CORREO.match(correo) or len(correo) > 254:
        await enviar_con_reintentos(
            update.message,
            "⚠️ El correo no parece válido. Por favor, escribe un correo como `ejemplo@correo.com`:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return PASO_CORREO

    context.user_data["reporte"]["correo"] = correo
    logger.info(f"Reporte en progreso - Correo: {correo}")

    teclado = ReplyKeyboardMarkup(
        [
            [KeyboardButton("📱 Compartir mi número", request_contact=True)],
            [KeyboardButton("Omitir teléfono ⏭️")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await enviar_con_reintentos(
        update.message,
        "📞 *Paso 3 de 7: Teléfono de contacto (Opcional)*\n\n"
        "Puedes presionar el botón *Compartir mi número*, escribirlo manualmente, o presionar *Omitir*:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=teclado,
    )
    return PASO_TELEFONO


async def recibir_telefono(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    telefono = None

    if msg.contact:
        telefono = msg.contact.phone_number
    elif msg.text:
        texto = msg.text.strip()
        if "omitir" in texto.lower():
            telefono = None
        elif RE_TELEFONO.match(texto):
            telefono = texto
        else:
            await enviar_con_reintentos(
                msg,
                "⚠️ El teléfono solo debe tener números, espacios y signos +, ( ), -.\n"
                "Inténtalo de nuevo o escribe 'Omitir':"
            )
            return PASO_TELEFONO

    context.user_data["reporte"]["telefono"] = telefono

    botones = []
    for codigo, etiqueta in TIPOS_FUGA.items():
        botones.append([InlineKeyboardButton(f"💧 {etiqueta}", callback_data=f"tipo_{codigo}")])

    await enviar_con_reintentos(
        msg,
        "🚰 *Paso 4 de 7: Tipo de fuga de agua*\n\n"
        "Selecciona la opción que mejor describa la situación:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(botones),
    )
    return PASO_TIPO_FUGA


async def recibir_tipo_fuga(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    codigo_tipo = query.data.replace("tipo_", "")
    if codigo_tipo not in TIPOS_FUGA:
        await enviar_con_reintentos(query.message, "Opción no válida. Por favor, selecciona una de las opciones.")
        return PASO_TIPO_FUGA

    context.user_data["reporte"]["tipo_fuga"] = codigo_tipo
    tipo_texto = TIPOS_FUGA[codigo_tipo]

    try:
        await query.edit_message_text(
            f"✅ Tipo de fuga seleccionado: *{tipo_texto}*",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass

    await enviar_con_reintentos(
        query.message,
        "📝 *Paso 5 de 7: Descripción de la fuga*\n\n"
        "Describe brevemente lo que ocurre (mínimo 10 caracteres, máx 2000).\n"
        "_Ejemplo: 'Tubería rota con abundante salida de agua limpia frente a la casa #25, inundando el andén._'",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return PASO_DESCRIPCION


async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()

    if len(desc) < 10:
        await enviar_con_reintentos(
            update.message,
            "⚠️ Por favor, describe la fuga con un poco más de detalle (al menos 10 caracteres):"
        )
        return PASO_DESCRIPCION

    if len(desc) > 2000:
        desc = desc[:2000]

    context.user_data["reporte"]["descripcion"] = desc

    teclado = ReplyKeyboardMarkup(
        [[KeyboardButton("📍 Enviar mi ubicación actual (GPS)", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await enviar_con_reintentos(
        update.message,
        "📍 *Paso 6 de 7: Ubicación de la fuga*\n\n"
        "Para que la cuadrilla de atención llegue rápidamente, presiona el botón *Enviar mi ubicación actual* "
        "o toca el clip 📎 y selecciona *Ubicación*.\n\n"
        "_(Si estás reportando desde otro sitio, puedes escribir el barrio y la dirección de referencia en un mensaje)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=teclado,
    )
    return PASO_UBICACION


async def recibir_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    lat = None
    lng = None
    barrio = None
    direccion = None
    origen = "mapa"

    if msg.location:
        lat = msg.location.latitude
        lng = msg.location.longitude
        origen = "gps"
    elif msg.text:
        texto = msg.text.strip()
        m = re.match(r"^([+-]?\d+(?:\.\d+)?)[,\s]+([+-]?\d+(?:\.\d+)?)$", texto)
        if m:
            lat = float(m.group(1))
            lng = float(m.group(2))
        else:
            from config import Config
            lat = Config.MAPA_LAT
            lng = Config.MAPA_LNG
            direccion = texto[:255]
    elif msg.photo or (msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/")):
        # El usuario mandó la foto primero
        from config import Config
        lat = Config.MAPA_LAT
        lng = Config.MAPA_LNG
        direccion = "Ubicación reportada por Telegram"
        # Procesamos la foto y pasamos a confirmación
        context.user_data["reporte"]["latitud"] = round(lat, 7)
        context.user_data["reporte"]["longitud"] = round(lng, 7)
        context.user_data["reporte"]["origen_ubicacion"] = "mapa"
        context.user_data["reporte"]["barrio"] = None
        context.user_data["reporte"]["direccion_referencia"] = direccion
        return await recibir_foto(update, context)

    if lat is None or lng is None:
        await enviar_con_reintentos(
            msg,
            "⚠️ No pudimos obtener las coordenadas. Por favor presiona el botón '📍 Enviar mi ubicación actual' o comparte tu ubicación:"
        )
        return PASO_UBICACION

    context.user_data["reporte"]["latitud"] = round(lat, 7)
    context.user_data["reporte"]["longitud"] = round(lng, 7)
    context.user_data["reporte"]["origen_ubicacion"] = origen
    context.user_data["reporte"]["barrio"] = barrio
    context.user_data["reporte"]["direccion_referencia"] = direccion
    logger.info(f"Ubicación registrada: {lat}, {lng}")

    await enviar_con_reintentos(
        msg,
        f"✅ Ubicación registrada correctamente ({lat:.5f}, {lng:.5f}).\n\n"
        "📸 *Paso 7 de 7: Fotografía de la fuga*\n\n"
        "Envía una foto clara de la fuga usando la cámara o desde tu galería:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return PASO_FOTO


async def recibir_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    foto_obj = None

    if msg.photo:
        foto_obj = msg.photo[-1]
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("image/"):
        foto_obj = msg.document

    if not foto_obj:
        await enviar_con_reintentos(
            msg,
            "⚠️ Por favor, adjunta una fotografía clara como imagen o foto:"
        )
        return PASO_FOTO

    await enviar_con_reintentos(msg, "⏳ Procesando fotografía...")

    try:
        archivo_tg = await foto_obj.get_file()
        buf = io.BytesIO()
        await archivo_tg.download_to_memory(buf)
        buf.seek(0)
        buf.filename = getattr(foto_obj, "file_name", None) or "foto.jpg"

        from config import Config
        foto_bytes = procesar_foto(buf, max_mb=Config.MAX_FOTO_MB)
        context.user_data["reporte"]["foto_bytes"] = foto_bytes
        logger.info(f"Foto procesada con éxito ({len(foto_bytes)} bytes)")
    except ErrorValidacion as ev:
        msg_err = ev.errores.get("foto", "Error al procesar la imagen.")
        await enviar_con_reintentos(msg, f"⚠️ {msg_err}\nPor favor intenta enviar otra fotografía:")
        return PASO_FOTO
    except Exception as e:
        logger.exception("Error procesando foto desde Telegram")
        await enviar_con_reintentos(msg, "⚠️ No se pudo procesar la fotografía. Intenta de nuevo con otra foto:")
        return PASO_FOTO

    rep = context.user_data.get("reporte", {})
    tipo_str = TIPOS_FUGA.get(rep.get("tipo_fuga", ""), "Otro")

    resumen = (
        "📋 *Resumen del Reporte*\n"
        "────────────────────────\n"
        f"👤 *Ciudadano:* {rep.get('nombre_ciudadano')}\n"
        f"📧 *Correo:* {rep.get('correo')}\n"
        f"📞 *Teléfono:* {rep.get('telefono') or 'No especificado'}\n"
        f"💧 *Tipo de fuga:* {tipo_str}\n"
        f"📍 *Coordenadas:* {rep.get('latitud')}, {rep.get('longitud')}\n"
        f"📝 *Descripción:* {rep.get('descripcion')}\n"
        f"📸 *Fotografía:* Adjunta (optimizada)\n"
        "────────────────────────\n\n"
        "¿Confirmas que deseas enviar este reporte a la empresa de servicios públicos?"
    )

    teclado = [
        [
            InlineKeyboardButton("✅ Confirmar y Enviar", callback_data="confirmar_reporte"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_reporte"),
        ]
    ]
    await enviar_con_reintentos(
        msg,
        resumen,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(teclado),
    )
    return PASO_CONFIRMACION


async def confirmar_y_guardar_reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancelar_reporte":
        context.user_data.clear()
        try:
            await query.edit_message_text(
                "❌ Reporte cancelado. Puedes iniciar uno nuevo cuando quieras con */reportar*.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
        return ConversationHandler.END

    rep = context.user_data.get("reporte")
    if not rep:
        await enviar_con_reintentos(
            query.message, "La sesión ha expirado. Escribe */reportar* para comenzar de nuevo."
        )
        return ConversationHandler.END

    foto_bytes = rep.pop("foto_bytes", None)
    rep.pop("nombre_sugerido", None)

    from app import create_app
    flask_app = create_app()

    def _guardar():
        with flask_app.app_context():
            rep_obj = crear_reporte(rep, foto_bytes=foto_bytes)
            # Retornar el string del número de seguimiento directamente
            return rep_obj.numero_seguimiento

    try:
        codigo = await asyncio.to_thread(_guardar)
        logger.info(f"Reporte guardado en la base de datos con éxito: {codigo}")
    except Exception as e:
        logger.exception("Error guardando reporte en base de datos")
        await enviar_con_reintentos(
            query.message,
            "⚠️ Ocurrió un error al guardar tu reporte en el sistema. Por favor intenta nuevamente más tarde."
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()

    mensaje_exito = (
        "🎉 *¡Reporte registrado con éxito!*\n\n"
        f"Tu número de seguimiento es:\n"
        f"`{codigo}`\n\n"
        f"📌 *Guarda este código.* Con él podrás consultar el estado de tu reporte en cualquier momento:\n"
        f"• Escribiendo aquí: `/consultar {codigo}`\n"
        f"• O en nuestro sitio web oficial.\n\n"
        f"💧 _¡Gracias por ayudar a cuidar el agua y contribuir al ODS 6!_"
    )

    try:
        await query.edit_message_text(mensaje_exito, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await enviar_con_reintentos(query.message, mensaje_exito, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END


# ==============================================================================
# FLUJO DE CONSULTA DE ESTADO
# ==============================================================================

async def comando_consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta directa por comando o solicita el código."""
    args = context.args
    if args:
        codigo = args[0]
        await responder_consulta(update, codigo)
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()
        msg = update.callback_query.message
    else:
        msg = update.message

    await enviar_con_reintentos(
        msg,
        "🔍 *Consulta de Reporte de Fuga*\n\n"
        "Por favor escribe el número de seguimiento (ejemplo: `ECO-2026-00001`):",
        parse_mode=ParseMode.MARKDOWN,
    )
    return PASO_CONSULTA


async def recibir_codigo_consulta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    codigo = update.message.text.strip()
    await responder_consulta(update, codigo)
    return ConversationHandler.END


async def responder_consulta(update: Update, codigo_raw: str):
    codigo = normalizar_seguimiento(codigo_raw)
    msg = update.effective_message

    if not codigo:
        await enviar_con_reintentos(
            msg,
            f"⚠️ El código «{codigo_raw}» no tiene un formato válido.\n"
            f"El formato debe ser como `ECO-AAAA-NNNNN` (ejemplo: `ECO-2026-00001`).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    from app import create_app
    flask_app = create_app()

    def _consultar():
        with flask_app.app_context():
            rep = Reporte.query.filter_by(numero_seguimiento=codigo).first()
            if not rep:
                return None
            return {
                "numero": rep.numero_seguimiento,
                "estado": rep.estado,
                "estado_texto": rep.estado_texto,
                "tipo": rep.tipo_fuga_texto,
                "descripcion": rep.descripcion,
                "fecha": formatear_fecha(rep.fecha_creacion),
                "historial": [
                    {
                        "estado": h.estado_nuevo_texto,
                        "fecha": formatear_fecha(h.fecha),
                        "nota": h.nota,
                    }
                    for h in rep.historial
                ],
            }

    datos = await asyncio.to_thread(_consultar)

    if not datos:
        await enviar_con_reintentos(
            msg,
            f"🔍 No se encontró ningún reporte con el número `{codigo}`.\n"
            f"Verifica que esté bien escrito e inténtalo nuevamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    emoji = EMOJIS_ESTADO.get(datos["estado"], "⚪")
    historial_texto = ""
    for h in datos["historial"]:
        nota_str = f" - _{h['nota']}_" if h["nota"] else ""
        historial_texto += f"• *{h['fecha']}* · {h['estado']}{nota_str}\n"

    texto_rep = (
        f"📊 *Estado del Reporte {datos['numero']}*\n"
        f"────────────────────────\n"
        f"🏷️ *Estado actual:* {emoji} *{datos['estado_texto'].upper()}*\n"
        f"📅 *Fecha de creación:* {datos['fecha']}\n"
        f"💧 *Tipo de fuga:* {datos['tipo']}\n"
        f"📝 *Descripción:* {datos['descripcion']}\n\n"
        f"📜 *Historial de atenciones:*\n"
        f"{historial_texto or '• Sin cambios registrados\n'}"
        f"────────────────────────"
    )

    await enviar_con_reintentos(msg, texto_rep, parse_mode=ParseMode.MARKDOWN)


async def callback_info_ods6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = (
        "🌍 *ODS 6: Agua limpia y saneamiento*\n\n"
        "Garantizar la disponibilidad de agua y su gestión sostenible y el saneamiento para todos.\n\n"
        "🎯 *Meta 6.4:* Para 2030, aumentar sustancialmente el uso eficiente de los recursos hídricos en todos los sectores.\n\n"
        "EcoAgua conecta a los ciudadanos con la empresa de acueducto para reparar fugas rápidamente y evitar el desperdicio del agua potable."
    )
    await enviar_con_reintentos(query.message, texto, parse_mode=ParseMode.MARKDOWN)


async def error_global(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra errores globales y avisa amistosamente al usuario."""
    logger.error("Error no controlado capturado por el bot:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await enviar_con_reintentos(
                update.effective_message,
                "⚠️ Hubo una breve interrupción en la conexión. Por favor reenvía tu último mensaje o escribe /start para reiniciar."
            )
        except Exception:
            pass


# ==============================================================================
# CONFIGURACIÓN Y EJECUCIÓN DEL BOT
# ==============================================================================

def construir_aplicacion(token: str) -> Application:
    """Construye y configura los manejadores del bot con tiempos de espera amplios."""
    request_config = HTTPXRequest(
        connection_pool_size=16,
        read_timeout=60.0,
        write_timeout=60.0,
        connect_timeout=30.0,
        pool_timeout=30.0,
    )
    app_bot = ApplicationBuilder().token(token).request(request_config).build()

    # Flujo conversacional de reporte
    conv_reporte = ConversationHandler(
        entry_points=[
            CommandHandler("reportar", iniciar_reporte),
            CallbackQueryHandler(iniciar_reporte, pattern="^btn_iniciar_reporte$"),
        ],
        per_message=False,
        states={
            PASO_NOMBRE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_nombre),
            ],
            PASO_CORREO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_correo),
            ],
            PASO_TELEFONO: [
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), recibir_telefono),
            ],
            PASO_TIPO_FUGA: [
                CallbackQueryHandler(recibir_tipo_fuga, pattern="^tipo_"),
            ],
            PASO_DESCRIPCION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion),
            ],
            PASO_UBICACION: [
                MessageHandler(filters.LOCATION, recibir_ubicacion),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, recibir_ubicacion),
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_ubicacion),
            ],
            PASO_FOTO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, recibir_foto),
            ],
            PASO_CONFIRMACION: [
                CallbackQueryHandler(confirmar_y_guardar_reporte, pattern="^(confirmar_reporte|cancelar_reporte)$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", comando_cancelar),
            CommandHandler("start", comando_start),
        ],
        allow_reentry=True,
    )

    # Flujo conversacional de consulta
    conv_consulta = ConversationHandler(
        entry_points=[
            CommandHandler("consultar", comando_consultar),
            CallbackQueryHandler(comando_consultar, pattern="^btn_iniciar_consulta$"),
        ],
        per_message=False,
        states={
            PASO_CONSULTA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_codigo_consulta),
            ],
        },
        fallbacks=[
            CommandHandler("cancelar", comando_cancelar),
            CommandHandler("start", comando_start),
        ],
        allow_reentry=True,
    )

    app_bot.add_handler(CommandHandler("start", comando_start))
    app_bot.add_handler(CommandHandler("ayuda", comando_ayuda))
    app_bot.add_handler(CommandHandler("cancelar", comando_cancelar))
    app_bot.add_handler(CallbackQueryHandler(callback_info_ods6, pattern="^btn_info_ods6$"))
    app_bot.add_handler(conv_reporte)
    app_bot.add_handler(conv_consulta)
    app_bot.add_error_handler(error_global)

    return app_bot


def iniciar_bot():
    """Inicia el bot en modo polling (desarrollo y pruebas locales)."""
    token = _obtener_token()
    if not token or token == "TU_TOKEN_DE_TELEGRAM":
        print("\n" + "=" * 60)
        print("❌ ERROR: TELEGRAM_BOT_TOKEN no está configurado.")
        print("Por favor crea tu bot con @BotFather en Telegram y coloca")
        print("el token en el archivo .env:")
        print("  TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
        print("=" * 60 + "\n")
        sys.exit(1)

    print("🤖 Iniciando Bot de Telegram de EcoAgua...")
    print("📡 Modo: Polling con HTTPXRequest optimizado...")

    app_bot = construir_aplicacion(token)
    app_bot.run_polling()


if __name__ == "__main__":
    iniciar_bot()
