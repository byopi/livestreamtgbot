import asyncio
import logging
import shutil
from dataclasses import dataclass, field
import imageio_ffmpeg

logger = logging.getLogger(__name__)

# Usa ffmpeg del sistema si está disponible, si no el de imageio-ffmpeg
FFMPEG_BIN = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()
logger.info("FFmpeg binario: %s", FFMPEG_BIN)


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

    destination = f"{rtmp_url.rstrip('/')}/{stream_key}"

    cmd = [
        FFMPEG_BIN,
        "-re",
        "-loglevel", "warning",
        "-i", source_url,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-profile:v", "baseline",
        "-level", "3.1",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-pix_fmt", "yuv420p",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "128k",
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

    asyncio.create_task(_watch(channel_id, process))
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


async def _watch(channel_id: int, process: asyncio.subprocess.Process):
    _, stderr_data = await process.communicate()
    if stderr_data:
        logger.warning("FFmpeg stderr (canal %s): %s",
                       channel_id, stderr_data.decode(errors="replace")[:500])
    _active.pop(channel_id, None)
    logger.info("🔴 FFmpeg terminó solo para canal=%s (rc=%s)",
                channel_id, process.returncode)
