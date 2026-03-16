import asyncio
import logging
import shutil
from dataclasses import dataclass, field
import imageio_ffmpeg
import yt_dlp

logger = logging.getLogger(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
logger.info("FFmpeg binario: %s", FFMPEG_BIN)

YTDLP_DOMAINS = ("youtube.com", "youtu.be", "twitch.tv", "twitter.com", "x.com")
DIRECT_KEYWORDS = (".m3u8", ".mp4", ".ts", ".flv", "rtmp://", "rtmps://")


def needs_ytdlp(url: str) -> bool:
    url_lower = url.lower()
    if any(kw in url_lower for kw in DIRECT_KEYWORDS):
        return False
    if any(d in url_lower for d in YTDLP_DOMAINS):
        return True
    return False


def extract_direct_url(url: str) -> str | None:
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            direct = info.get("url") or (info.get("formats", [{}])[-1].get("url"))
            logger.info("URL directa extraída: %s...", str(direct)[:80])
            return direct
    except Exception as e:
        logger.error("yt-dlp error: %s", e)
        return None


@dataclass
class StreamSession:
    channel_id: int
    channel_name: str
    source_url: str
    process: asyncio.subprocess.Process = field(default=None, repr=False)


_active: dict[int, StreamSession] = {}


def is_streaming(channel_id: int) -> bool:
    return channel_id in _active


def active_streams() -> dict[int, StreamSession]:
    return dict(_active)


async def start_stream(channel_id: int, channel_name: str,
                       rtmp_url: str, stream_key: str,
                       source_url: str) -> bool:
    if is_streaming(channel_id):
        logger.warning("Canal %s ya está en stream", channel_id)
        return False

    actual_url = source_url

    if needs_ytdlp(source_url):
        logger.info("Extrayendo URL directa para: %s", source_url)
        loop = asyncio.get_event_loop()
        direct = await loop.run_in_executor(None, extract_direct_url, source_url)
        if direct:
            actual_url = direct
        else:
            logger.error("No se pudo extraer URL directa")
            return False
    else:
        logger.info("URL directa detectada, pasando directo a FFmpeg")

    destination = f"{rtmp_url.rstrip('/')}/{stream_key}"

    cmd = [
        FFMPEG_BIN,
        "-re",
        "-loglevel", "warning",
        "-fflags", "+discardcorrupt+nobuffer+genpts",
        "-err_detect", "ignore_err",
        "-i", actual_url,
        # Reencoding para garantizar compatibilidad con RTMP/FLV
        "-vf", "scale=1280:720",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-profile:v", "baseline",
        "-level", "3.1",
        "-b:v", "1500k",
        "-maxrate", "1500k",
        "-bufsize", "3000k",
        "-pix_fmt", "yuv420p",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "96k",
        "-ar", "44100",
        "-f", "flv",
        destination,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("FFmpeg no encontrado en: %s", FFMPEG_BIN)
        return False

    session = StreamSession(
        channel_id=channel_id,
        channel_name=channel_name,
        source_url=source_url,
        process=process,
    )
    _active[channel_id] = session

    asyncio.create_task(_watch(channel_id, process, rtmp_url, stream_key, source_url))
    logger.info("▶️  Stream iniciado canal=%s pid=%s", channel_id, process.pid)
    return True


async def stop_stream(channel_id: int) -> bool:
    session = _active.pop(channel_id, None)
    if session is None:
        return False

    proc = session.process
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()

    logger.info("⏹  Stream detenido canal=%s", channel_id)
    return True


async def _watch(channel_id: int, process: asyncio.subprocess.Process,
                 rtmp_url: str = "", stream_key: str = "",
                 source_url: str = ""):
    _, stderr_data = await process.communicate()
    stderr_text = stderr_data.decode(errors="replace") if stderr_data else ""
    if stderr_text:
        logger.warning("FFmpeg stderr (canal %s): %s", channel_id, stderr_text[:500])
    _active.pop(channel_id, None)
    logger.info("🔴 FFmpeg terminó canal=%s (rc=%s)", channel_id, process.returncode)
