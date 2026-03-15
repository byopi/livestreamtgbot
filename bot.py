import asyncio
import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler
)
from config import BOT_TOKEN
from database import init_db
from handlers.menu import start_handler, menu_callback
from handlers.channels import (
    add_channel_start, add_channel_name, add_channel_rtmp,
    add_channel_key, delete_channel_callback,
    CHANNEL_NAME, CHANNEL_RTMP, CHANNEL_KEY
)
from handlers.stream import stream_url_received, stop_stream_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── Servidor HTTP mínimo para que Render no mate el servicio ─────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # silencia los logs de cada request


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info("🌐 Health server escuchando en puerto %s", port)
    server.serve_forever()
# ────────────────────────────────────────────────────────────────────


async def post_init(app):
    await init_db()
    logger.info("✅ Base de datos iniciada")


def main():
    # Arranca el health server en un hilo separado (no bloquea el bot)
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Conversación: agregar canal (3 pasos) ────────────────────────
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_channel_start, pattern="^add_channel$")],
        states={
            CHANNEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_name)],
            CHANNEL_RTMP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_rtmp)],
            CHANNEL_KEY:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_key)],
        },
        fallbacks=[CommandHandler("start", start_handler)],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(add_channel_conv)
    app.add_handler(CallbackQueryHandler(stop_stream_callback, pattern=r"^stop_stream:\d+$"))
    app.add_handler(CallbackQueryHandler(delete_channel_callback, pattern=r"^delete_channel:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, stream_url_received))
    app.add_handler(CallbackQueryHandler(menu_callback))

    logger.info("🤖 Bot iniciado y escuchando...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
