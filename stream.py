from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import get_channel
from streamer import start_stream, stop_stream, is_streaming
from config import MAX_STREAMS, ADMIN_IDS

STREAM_URL = 10   # estado de conversación


async def stream_url_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Recibe la URL m3u8 (o cualquier URL de video) y arranca el stream.
    Se activa cuando user_data["waiting_stream_url"] == True.
    """
    if not context.user_data.get("waiting_stream_url"):
        return   # no estamos esperando nada

    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return

    channel_id = context.user_data.pop("pending_stream_channel", None)
    context.user_data.pop("waiting_stream_url", None)

    if channel_id is None:
        await update.message.reply_text("⚠️ Error: no se encontró el canal seleccionado.")
        return

    source_url = update.message.text.strip()

    # Validación mínima
    if not (source_url.startswith("http://") or source_url.startswith("https://")
            or source_url.startswith("rtmp")):
        await update.message.reply_text(
            "⚠️ URL no válida. Debe comenzar con `http://`, `https://` o `rtmp://`.\n"
            "Inténtalo de nuevo desde el menú.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    channel = await get_channel(channel_id)
    if not channel or channel["owner_id"] != uid:
        await update.message.reply_text("⚠️ Canal no encontrado.")
        return

    if is_streaming(channel_id):
        await update.message.reply_text(f"⚠️ *{channel['name']}* ya está transmitiendo.")
        return

    # Límite de streams simultáneos
    from streamer import active_streams
    if len(active_streams()) >= MAX_STREAMS:
        await update.message.reply_text(
            f"⚠️ Límite de streams simultáneos alcanzado (`{MAX_STREAMS}`).\n"
            "Detén alguno antes de iniciar otro.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text(
        f"⏳ Iniciando stream en *{channel['name']}*...",
        parse_mode=ParseMode.MARKDOWN,
    )

    ok = await start_stream(
        channel_id=channel["id"],
        channel_name=channel["name"],
        rtmp_url=channel["rtmp_url"],
        stream_key=channel["stream_key"],
        source_url=source_url,
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏹ Detener este stream", callback_data=f"stop_stream:{channel_id}")],
        [InlineKeyboardButton("⬅️ Menú principal", callback_data="main_menu")],
    ])

    if ok:
        await msg.edit_text(
            f"🟢 *Stream iniciado*\n\n"
            f"📺 Canal: *{channel['name']}*\n"
            f"🔗 Fuente: `{source_url}`\n\n"
            "El stream seguirá activo hasta que lo detengas manualmente o se agote la fuente.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await msg.edit_text(
            "❌ No se pudo iniciar el stream. Comprueba que FFmpeg esté instalado "
            "y que la URL sea accesible.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Menú principal", callback_data="main_menu")]
            ]),
        )


async def stop_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detiene el stream de un canal."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if uid not in ADMIN_IDS:
        await query.answer("🚫 Sin permiso.", show_alert=True)
        return

    channel_id = int(query.data.split(":")[1])
    channel = await get_channel(channel_id)

    if not channel or channel["owner_id"] != uid:
        await query.answer("Canal no encontrado.", show_alert=True)
        return

    stopped = await stop_stream(channel_id)

    if stopped:
        text = f"⏹ Stream de *{channel['name']}* detenido correctamente."
    else:
        text = f"ℹ️ *{channel['name']}* no estaba transmitiendo."

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Menú principal", callback_data="main_menu")]
        ]),
        parse_mode=ParseMode.MARKDOWN,
    )
