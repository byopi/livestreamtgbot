from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import add_channel, delete_channel, get_channel
from streamer import stop_stream, is_streaming

# Estados de la conversación
CHANNEL_NAME = 0
CHANNEL_RTMP = 1
CHANNEL_KEY  = 2


async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el flujo de agregar canal."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "➕ *Agregar Canal — Paso 1/3*\n\n"
        "Escribe un *nombre* para identificar este canal (ej: `Mi Canal de Noticias`).",
        parse_mode=ParseMode.MARKDOWN,
    )
    return CHANNEL_NAME


async def add_channel_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el nombre y pide RTMP URL."""
    context.user_data["ch_name"] = update.message.text.strip()
    await update.message.reply_text(
        "➕ *Agregar Canal — Paso 2/3*\n\n"
        "Envía la *URL del servidor RTMP* de Telegram.\n"
        "La encuentras en tu canal → *Iniciar transmisión en vivo* → *Transmitir con...*\n\n"
        "Suele tener este formato:\n`rtmps://dc4-1.rtmp.t.me/s/`",
        parse_mode=ParseMode.MARKDOWN,
    )
    return CHANNEL_RTMP


async def add_channel_rtmp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda la RTMP URL y pide el stream key."""
    url = update.message.text.strip()
    if not url.startswith("rtmp"):
        await update.message.reply_text(
            "⚠️ La URL debe comenzar con `rtmps://` o `rtmp://`.\nIntenta de nuevo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return CHANNEL_RTMP

    context.user_data["ch_rtmp"] = url
    await update.message.reply_text(
        "➕ *Agregar Canal — Paso 3/3*\n\n"
        "Envía el *Stream Key* (clave de transmisión) de tu canal de Telegram.\n"
        "Es el código largo que aparece junto a la URL RTMP.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return CHANNEL_KEY


async def add_channel_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda el stream key y finaliza."""
    uid = update.effective_user.id
    key  = update.message.text.strip()
    name = context.user_data.get("ch_name", "Sin nombre")
    rtmp = context.user_data.get("ch_rtmp", "")

    ch_id = await add_channel(uid, name, rtmp, key)
    context.user_data.clear()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="main_menu")]
    ])
    await update.message.reply_text(
        f"✅ *Canal guardado correctamente*\n\n"
        f"🆔 ID interno: `{ch_id}`\n"
        f"📺 Nombre: *{name}*\n\n"
        "Ya puedes usarlo para iniciar un stream.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )
    return ConversationHandler.END


async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina un canal; si está en stream, lo detiene primero."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    channel_id = int(query.data.split(":")[1])

    channel = await get_channel(channel_id)
    if not channel or channel["owner_id"] != uid:
        await query.answer("No encontrado o sin permiso.", show_alert=True)
        return

    if is_streaming(channel_id):
        await stop_stream(channel_id)

    await delete_channel(channel_id, uid)

    await query.edit_message_text(
        f"🗑 Canal *{channel['name']}* eliminado correctamente.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="main_menu")]
        ]),
        parse_mode=ParseMode.MARKDOWN,
    )


# Necesario para ConversationHandler.END
from telegram.ext import ConversationHandler
