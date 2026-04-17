from pathlib import Path
from typing import Dict, List, Optional

from .constants import FONT_PATH
from .profile_engine import build_resolution_filter, normalize_filter_list, normalize_profile


def escape_drawtext_text(text: str) -> str:
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace("'", "\\'")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("%", "\\%")
    return escaped


def build_drawtext(text: str, x: str, y: str, font_path: str) -> str:
    safe_text = escape_drawtext_text(text)
    safe_font = (font_path or FONT_PATH).replace("\\", "/")
    safe_font = safe_font.replace(":", "\\:").replace("'", "\\'")
    return (
        f"drawtext=fontfile='{safe_font}':text='{safe_text}':"
        f"x={x}:y={y}:fontsize=48:fontcolor=white"
    )


def build_ffmpeg_command(
    source_path: Path,
    target_path: Path,
    profile: Dict[str, object],
    record_no: Optional[str],
    origin_name: str,
) -> List[str]:
    profile = normalize_profile(profile)
    vf_filters: List[str] = []
    af_filters: List[str] = []

    resolution_filter = build_resolution_filter(profile)
    if resolution_filter:
        vf_filters.append(resolution_filter)

    vf_filters.extend(normalize_filter_list(profile.get("video_filters_base")))
    af_filters.extend(normalize_filter_list(profile.get("audio_filters_base")))

    font_path = str(profile.get("font_path", FONT_PATH)).strip()

    if profile["add_record_watermark"] and record_no:
        vf_filters.append(build_drawtext(record_no, "w-tw-20", "h-th-20", font_path))

    if profile["add_origin_name_watermark"]:
        vf_filters.append(build_drawtext(origin_name, "20", "h-th-20", font_path))

    cmd = ["ffmpeg"]
    hwaccel = str(profile.get("hwaccel", "")).strip()
    if hwaccel:
        cmd.extend(["-hwaccel", hwaccel])

    cmd.extend(["-i", str(source_path)])

    if vf_filters:
        cmd.extend(["-vf", ", ".join(vf_filters)])

    if af_filters:
        cmd.extend(["-af", ", ".join(af_filters)])

    video_codec = str(profile.get("video_codec", "")).strip()
    if video_codec:
        cmd.extend(["-c:v", video_codec])

    video_bitrate = str(profile.get("video_bitrate", "")).strip()
    if video_bitrate:
        cmd.extend(["-b:v", video_bitrate])

    fps = str(profile.get("fps", "")).strip()
    if fps:
        cmd.extend(["-r", fps])

    audio_codec = str(profile.get("audio_codec", "")).strip()
    if audio_codec:
        cmd.extend(["-c:a", audio_codec])

    audio_bitrate = str(profile.get("audio_bitrate", "")).strip()
    if audio_bitrate:
        cmd.extend(["-b:a", audio_bitrate])

    audio_sample_rate = str(profile.get("audio_sample_rate", "")).strip()
    if audio_sample_rate:
        cmd.extend(["-ar", audio_sample_rate])

    cmd.extend(normalize_filter_list(profile.get("extra_output_args")))
    cmd.append(str(target_path))

    return cmd
