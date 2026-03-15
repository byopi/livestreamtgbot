import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StreamSession:
    channel_id: int
    channel_name: str
    source_url: str
    process: asyncio.subprocess.Process = field(default=None, repr=False)


# channel_id -> StreamSession
_active: dict[int, StreamSession] = {}


def is_streaming(channel_id: int) -> bool:
    return channel_id in _active


def active_streams() -> dict[int, StreamSession]:
    return dict(_active)


async def start_stream(channel_id: int, channel_name: str,
                       rtmp_url: str, stream_key: str,
                       source_url: str) -> bool:
    """
    Lanza FFmpeg para retransmitir source_url (m3u8 u otro) al endpoint RTMP.
    Devuelve True si arrancó, False si ya estaba activo o falló.
    """
    if is_streaming(channel_id):
        logger.warning("Canal %s ya está en stream", channel_id)
        return False

    destination = f"{rtmp_url.rstrip('/')}/{stream_key}"

    cmd = [
        "ffmpeg",
        "-re",
        "-loglevel", "warning",
        # --- Input ---
        "-i", source_url,
        # --- Video: re-encode a H.264 baseline (compatible Telegram) ---
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-profile:v", "baseline",
        "-level", "3.1",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-pix_fmt", "yuv420p",
        "-g", "60",                 # keyframe cada 2 s a 30fps
        # --- Audio: AAC ---
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        # --- Output RTMP ---
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
        logger.error("FFmpeg no encontrado. Instálalo en el servidor.")
        return False

    session = StreamSession(
        channel_id=channel_id,
        channel_name=channel_name,
        source_url=source_url,
        process=process,
    )
    _active[channel_id] = session

    # Tarea de fondo: monitorea el proceso
    asyncio.create_task(_watch(channel_id, process))
    logger.info("▶️  Stream iniciado canal=%s pid=%s", channel_id, process.pid)
    return True


async def stop_stream(channel_id: int) -> bool:
    """
    Detiene el stream de un canal. Devuelve True si había algo activo.
    """
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


async def _watch(channel_id: int, process: asyncio.subprocess.Process):
    """Limpia el dict cuando FFmpeg termina solo (fin del archivo, error, etc.)."""
    _, stderr_data = await process.communicate()
    if stderr_data:
        logger.warning("FFmpeg stderr (canal %s): %s",
                       channel_id, stderr_data.decode(errors="replace")[:500])
    _active.pop(channel_id, None)
    logger.info("🔴 FFmpeg terminó solo para canal=%s (rc=%s)",
                channel_id, process.returncode)
