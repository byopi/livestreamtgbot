import os

BOT_TOKEN = os.environ["BOT_TOKEN"]

# IDs de admins separados por coma: "123456,789012"
_raw_admins = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw_admins.split(",") if x.strip()]

MAX_STREAMS = int(os.environ.get("MAX_STREAMS", "5"))
LOG_CHANNEL  = os.environ.get("LOG_CHANNEL", "")   # opcional, ID de canal de logs
DB_PATH      = os.environ.get("DB_PATH", "/data/bot.db")
