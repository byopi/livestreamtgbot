import asyncio
import logging
import shutil
from dataclasses import dataclass, field
import imageio_ffmpeg
import yt_dlp

logger = logging.getLogger(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
logger.info("FFmpeg binario: %s", FFMPEG_BIN)

YOUTUBE_DOMAINS = ("youtube.com", "youtu.be", "www.youtube.com")


def is_youtube(url: str) -> bool:
    return any(d in url for d in YOUTUBE_DOMAINS)


def extract_direct_url(url: str) -> str | None:
    """Extrae la URL directa del stream usando yt-dlp."""
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

    # Si es YouTube u otra plataforma, extraer URL directa
    actual_url = source_url
    if is_youtube(source_url) or not source_url.endswith(".m3u8"):
        logger.info("Extrayendo URL directa para: %s", source_url)
        loop = asyncio.get_event_loop()
        direct = await loop.run_in_executor(None, extract_direct_url, source_url)
        if direct:
            actual_url = direct
        else:
            logger.error("No se pudo extraer URL directa")
            return False

    destination = f"{rtmp_url.rstrip('/')}/{stream_key}"

    cmd = [
        FFMPEG_BIN,
        "-re",
        "-loglevel", "warning",
        "-i", actual_url,
        "-c:v", "copy",
        "-c:a", "copy",
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
