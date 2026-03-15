from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS
from database import get_channels
from streamer import active_streams, is_streaming


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = (update.effective_user or update.callback_query.from_user).id
        if not is_admin(uid):
            if update.callback_query:
                await update.callback_query.answer("🚫 No tienes permiso.", show_alert=True)
            else:
                await update.message.reply_text("🚫 No tienes permiso para usar este bot.")
            return
        return await func(update, context)
    return wrapper


async def build_main_menu(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    channels = await get_channels(user_id)
    active = active_streams()

    streaming_count = sum(1 for ch in channels if ch["id"] in active)

    text = (
        "📡 *TG RTMP MultiBot*\n\n"
        f"Canales registrados: *{len(channels)}*\n"
        f"Streams activos: *{streaming_count}*\n\n"
        "_Selecciona una opción:_"
    )

    keyboard = [
        [InlineKeyboardButton("📺 Mis Canales", callback_data="my_channels")],
        [InlineKeyboardButton("▶️ Iniciar Stream", callback_data="start_stream_menu")],
        [InlineKeyboardButton("⏹ Detener Stream", callback_data="stop_stream_menu")],
        [InlineKeyboardButton("📊 Estado", callback_data="status")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


@admin_required
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text, markup = await build_main_menu(uid)
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


@admin_required
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    # ── Menú principal ──────────────────────────────────────────────
    if data == "main_menu":
        text, markup = await build_main_menu(uid)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

    # ── Mis Canales ─────────────────────────────────────────────────
    elif data == "my_channels":
        channels = await get_channels(uid)
        active = active_streams()

        if not channels:
            text = "📺 *Mis Canales*\n\nNo tienes canales registrados aún."
        else:
            lines = []
            for ch in channels:
                estado = "🟢 en vivo" if ch["id"] in active else "⚫ inactivo"
                lines.append(f"• *{ch['name']}* — {estado}")
            text = "📺 *Mis Canales*\n\n" + "\n".join(lines)

        keyboard = [
            [InlineKeyboardButton("➕ Agregar Canal", callback_data="add_channel")],
        ]
        if channels:
            keyboard.append(
                [InlineKeyboardButton("🗑 Eliminar Canal", callback_data="delete_channel_menu")]
            )
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard),
                                      parse_mode=ParseMode.MARKDOWN)

    # ── Iniciar stream: elegir canal ─────────────────────────────────
    elif data == "start_stream_menu":
        channels = await get_channels(uid)
        active = active_streams()
        disponibles = [ch for ch in channels if ch["id"] not in active]

        if not channels:
            await query.edit_message_text(
                "⚠️ No tienes canales registrados.\nVe a *Mis Canales* → *Agregar Canal*.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if not disponibles:
            await query.edit_message_text(
                "⚠️ Todos tus canales ya están transmitiendo.\nDetén alguno primero.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")]]),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        keyboard = [
            [InlineKeyboardButton(ch["name"], callback_data=f"stream_select:{ch['id']}")]
            for ch in disponibles
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")])
        await query.edit_message_text(
            "▶️ *Iniciar Stream*\n\nSelecciona el canal donde quieres transmitir:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Selección de canal para stream ──────────────────────────────
    elif data.startswith("stream_select:"):
        channel_id = int(data.split(":")[1])
        context.user_data["pending_stream_channel"] = channel_id
        await query.edit_message_text(
            "🔗 Envíame el enlace `.m3u8` (u otra URL de video/stream) para transmitir en este canal.\n\n"
            "Puedes enviar `/start` para cancelar.",
            parse_mode=ParseMode.MARKDOWN,
        )
        context.user_data["waiting_stream_url"] = True

    # ── Detener stream: elegir canal ─────────────────────────────────
    elif data == "stop_stream_menu":
        channels = await get_channels(uid)
        active = active_streams()
        en_vivo = [ch for ch in channels if ch["id"] in active]

        if not en_vivo:
            await query.edit_message_text(
                "ℹ️ No hay streams activos en este momento.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")]]),
            )
            return

        keyboard = [
            [InlineKeyboardButton(f"⏹ {ch['name']}", callback_data=f"stop_stream:{ch['id']}")]
            for ch in en_vivo
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")])
        await query.edit_message_text(
            "⏹ *Detener Stream*\n\nSelecciona el canal a detener:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Eliminar canal: elegir cuál ──────────────────────────────────
    elif data == "delete_channel_menu":
        channels = await get_channels(uid)
        if not channels:
            await query.edit_message_text("No tienes canales para eliminar.")
            return
        keyboard = [
            [InlineKeyboardButton(f"🗑 {ch['name']}", callback_data=f"delete_channel:{ch['id']}")]
            for ch in channels
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Volver", callback_data="my_channels")])
        await query.edit_message_text(
            "🗑 *Eliminar Canal*\n\nSelecciona el canal a eliminar:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Estado global ─────────────────────────────────────────────────
    elif data == "status":
        channels = await get_channels(uid)
        active = active_streams()

        if not active:
            text = "📊 *Estado*\n\n⚫ No hay streams activos."
        else:
            lines = []
            for ch in channels:
                if ch["id"] in active:
                    session = active[ch["id"]]
                    lines.append(
                        f"🟢 *{ch['name']}*\n"
                        f"   └ `{session.source_url}`"
                    )
            text = "📊 *Estado — Streams Activos*\n\n" + "\n\n".join(lines)

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Actualizar", callback_data="status"),
                                                InlineKeyboardButton("⬅️ Volver", callback_data="main_menu")]]),
            parse_mode=ParseMode.MARKDOWN,
        )
