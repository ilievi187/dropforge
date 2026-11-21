"""DropForge backend — 100% offline media, video, audio & image converter powered by ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".wmv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".avif"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma"}


@dataclass(frozen=True)
class ConvertPreset:
    id: str
    title: str
    description: str
    kind: str  # video | image | audio
    output_ext: str
    suffix: str


PRESETS: list[ConvertPreset] = [
    # Video
    ConvertPreset("vid_discord", "Compress for Discord / Telegram", "Compact H.264 MP4 (720p, fast web-ready)", "video", ".mp4", "_discord"),
    ConvertPreset("vid_mp4", "Clean 1080p MP4 (H.264)", "High-compatibility MP4 with AAC audio", "video", ".mp4", "_1080p"),
    ConvertPreset("vid_gif", "Video → Smooth GIF", "15 FPS optimized 640px animated GIF", "video", ".gif", "_clip"),
    ConvertPreset("vid_mp3", "Extract Audio (MP3)", "192 kbps MP3 audio track only", "video", ".mp3", "_audio"),
    ConvertPreset("vid_mute", "Remove Audio (Mute)", "Lossless video copy with audio stripped", "video", ".mp4", "_muted"),
    # Image
    ConvertPreset("img_png", "Convert to PNG", "Lossless PNG image", "image", ".png", "_converted"),
    ConvertPreset("img_jpg", "Convert to JPG (High Quality)", "Universal compact JPEG", "image", ".jpg", "_converted"),
    ConvertPreset("img_webp", "Convert to WebP (Smallest)", "Modern web-optimized image", "image", ".webp", "_web"),
    ConvertPreset("img_resize", "Resize to 1920px Wide", "Preserves aspect ratio, great for sharing", "image", ".jpg", "_1920px"),
    ConvertPreset("img_strip", "Strip EXIF / Privacy Clean", "Removes GPS location & camera metadata", "image", ".png", "_clean"),
    # Audio
    ConvertPreset("aud_mp3", "Convert to MP3 (320k)", "High-bitrate universal MP3", "audio", ".mp3", "_320k"),
    ConvertPreset("aud_wav", "Convert to WAV (Lossless)", "Uncompressed PCM WAV", "audio", ".wav", "_pcm"),
    ConvertPreset("aud_opus", "Convert to Opus (Compact)", "Crystal clear small OGG/Opus file", "audio", ".ogg", "_opus"),
]


def detect_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    return "unknown"


def presets_for_file(path: Path) -> list[ConvertPreset]:
    kind = detect_kind(path)
    if kind == "unknown":
        return PRESETS
    return [p for p in PRESETS if p.kind == kind]


def human_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{n} B"


@dataclass
class ConvertResult:
    output_path: Path
    input_bytes: int
    output_bytes: int

    @property
    def summary(self) -> str:
        delta = ""
        if self.input_bytes > 0:
            pct = ((self.output_bytes - self.input_bytes) / self.input_bytes) * 100.0
            sign = "+" if pct > 0 else ""
            delta = f" ({sign}{pct:.0f}%)"
        return f"Saved {self.output_path.name} · {human_bytes(self.input_bytes)} → {human_bytes(self.output_bytes)}{delta}"


def run_conversion(input_path: Path, preset: ConvertPreset) -> ConvertResult:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed. Install it via your package manager (e.g. sudo pacman -S ffmpeg).")
    if not input_path.exists():
        raise RuntimeError(f"Input file not found: {input_path}")

    out_path = input_path.with_name(f"{input_path.stem}{preset.suffix}{preset.output_ext}")
    counter = 1
    while out_path.exists():
        out_path = input_path.with_name(f"{input_path.stem}{preset.suffix}_{counter}{preset.output_ext}")
        counter += 1

    inp = str(input_path)
    out = str(out_path)

    cmd_map: dict[str, list[str]] = {
        "vid_discord": ["ffmpeg", "-y", "-i", inp, "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out],
        "vid_mp4": ["ffmpeg", "-y", "-i", inp, "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264", "-crf", "22", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out],
        "vid_gif": ["ffmpeg", "-y", "-i", inp, "-vf", "fps=15,scale='min(640,iw)':-1:flags=lanczos", out],
        "vid_mp3": ["ffmpeg", "-y", "-i", inp, "-vn", "-c:a", "libmp3lame", "-b:a", "192k", out],
        "vid_mute": ["ffmpeg", "-y", "-i", inp, "-c:v", "copy", "-an", out],
        "img_png": ["ffmpeg", "-y", "-i", inp, out],
        "img_jpg": ["ffmpeg", "-y", "-i", inp, "-q:v", "2", out],
        "img_webp": ["ffmpeg", "-y", "-i", inp, "-quality", "82", out],
        "img_resize": ["ffmpeg", "-y", "-i", inp, "-vf", "scale='min(1920,iw)':-1", "-q:v", "2", out],
        "img_strip": ["ffmpeg", "-y", "-i", inp, "-map_metadata", "-1", out],
        "aud_mp3": ["ffmpeg", "-y", "-i", inp, "-c:a", "libmp3lame", "-b:a", "320k", out],
        "aud_wav": ["ffmpeg", "-y", "-i", inp, "-c:a", "pcm_s16le", out],
        "aud_opus": ["ffmpeg", "-y", "-i", inp, "-c:a", "libopus", "-b:a", "128k", out],
    }

    cmd = cmd_map[preset.id]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not out_path.exists():
        err_tail = "\n".join(res.stderr.strip().splitlines()[-6:])
        raise RuntimeError(err_tail or f"ffmpeg failed with exit code {res.returncode}")

    return ConvertResult(
        output_path=out_path,
        input_bytes=input_path.stat().st_size,
        output_bytes=out_path.stat().st_size,
    )
