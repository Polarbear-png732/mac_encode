import logging
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pypinyin import Style, lazy_pinyin

from .constants import FFMPEG_PROFILES, FONT_PATH, RULE_SETS, VIDEO_EXTENSIONS
from .models import Scene
from .records import normalize_series_name
from .runtime import display_path, scene_label


CHINESE_NUMBER_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNIT_MAP = {
    "十": 10,
    "百": 100,
    "千": 1000,
}

PROFILE_DEFAULTS = {
    "hwaccel": "videotoolbox",
    "font_path": FONT_PATH,
    "video_codec": "h264_videotoolbox",
    "video_bitrate": "8000k",
    "fps": "25",
    "audio_codec": "mp2",
    "audio_bitrate": "192k",
    "audio_sample_rate": "48000",
    "add_record_watermark": False,
    "add_origin_name_watermark": False,
    "resolution_strategy": "none",
    "resolution_value": "",
    "video_filters_base": [],
    "audio_filters_base": [],
    "extra_output_args": [],
}

HARDWARE_VIDEO_CODECS = {
    "h264_nvenc",
    "hevc_nvenc",
    "h264_videotoolbox",
    "hevc_videotoolbox",
    "h264_qsv",
    "hevc_qsv",
    "h264_amf",
    "hevc_amf",
}

HARDWARE_ERROR_KEYWORDS = (
    "unknown encoder",
    "encoder not found",
    "cannot load nvcuda",
    "no nvenc capable devices found",
    "device type cuda needed",
    "error while opening encoder",
    "hardware device",
    "initialization failed",
    "videotoolbox",
    "failed to initialise videotoolbox",
    "videotoolbox init",
    "vtcompression",
    "compression session",
    "cannot create compression session",
    "failed to create compression session",
    "hwaccel",
)

_RUNTIME_PROFILE_OVERRIDES: Dict[str, Dict[str, object]] = {}
_RUNTIME_RULE_SETS: Dict[str, List[Dict[str, object]]] = {}


def set_runtime_customization(
    profile_overrides: Optional[Dict[str, Dict[str, object]]] = None,
    rule_sets: Optional[Dict[str, List[Dict[str, object]]]] = None,
) -> None:
    global _RUNTIME_PROFILE_OVERRIDES, _RUNTIME_RULE_SETS
    _RUNTIME_PROFILE_OVERRIDES = profile_overrides or {}
    _RUNTIME_RULE_SETS = rule_sets or {}


def normalize_filter_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def normalize_profile(raw_profile: Optional[Dict[str, object]]) -> Dict[str, object]:
    profile = deepcopy(PROFILE_DEFAULTS)
    if raw_profile:
        profile.update(raw_profile)

    # 兼容旧字段：audio_filters -> audio_filters_base
    if raw_profile and "audio_filters" in raw_profile and not profile.get("audio_filters_base"):
        profile["audio_filters_base"] = raw_profile.get("audio_filters")

    profile["video_filters_base"] = normalize_filter_list(profile.get("video_filters_base"))
    profile["audio_filters_base"] = normalize_filter_list(profile.get("audio_filters_base"))
    profile["extra_output_args"] = normalize_filter_list(profile.get("extra_output_args"))
    return profile


def rule_matches(rule: Dict[str, object], source_path: Path, origin_name: str, scene: Scene) -> bool:
    match = rule.get("match", {})
    if not isinstance(match, dict):
        return False

    filename = source_path.name
    dirname = source_path.parent.name

    filename_regex = str(match.get("filename_regex", "")).strip()
    if filename_regex and not re.search(filename_regex, filename, flags=re.IGNORECASE):
        return False

    stem_regex = str(match.get("stem_regex", "")).strip()
    if stem_regex and not re.search(stem_regex, origin_name, flags=re.IGNORECASE):
        return False

    dirname_regex = str(match.get("dirname_regex", "")).strip()
    if dirname_regex and not re.search(dirname_regex, dirname, flags=re.IGNORECASE):
        return False

    scene_name = str(match.get("scene_name", "")).strip()
    if scene_name and scene.name != scene_name:
        return False

    return True


def apply_rule_to_profile(profile: Dict[str, object], rule: Dict[str, object]) -> Dict[str, object]:
    next_profile = deepcopy(profile)

    overrides = rule.get("overrides", {})
    if isinstance(overrides, dict):
        next_profile.update(overrides)

    video_filters_base = normalize_filter_list(next_profile.get("video_filters_base"))
    audio_filters_base = normalize_filter_list(next_profile.get("audio_filters_base"))
    video_filters_base.extend(normalize_filter_list(rule.get("append_video_filters")))
    audio_filters_base.extend(normalize_filter_list(rule.get("append_audio_filters")))
    next_profile["video_filters_base"] = video_filters_base
    next_profile["audio_filters_base"] = audio_filters_base

    return normalize_profile(next_profile)


def resolve_effective_profile(scene: Scene, source_path: Path, origin_name: str) -> Tuple[Dict[str, object], List[str]]:
    base_profile = FFMPEG_PROFILES.get(scene.profile_name)
    if not base_profile:
        raise ValueError(f"未定义的命令配置 profile: {scene.profile_name}")

    profile = normalize_profile(base_profile)

    runtime_override = _RUNTIME_PROFILE_OVERRIDES.get(scene.profile_name)
    if isinstance(runtime_override, dict):
        profile = normalize_profile({**profile, **runtime_override})

    rules = []
    default_rules = RULE_SETS.get(scene.rule_set_name, [])
    runtime_rules = _RUNTIME_RULE_SETS.get(scene.rule_set_name, [])
    if isinstance(default_rules, list):
        rules.extend(default_rules)
    if isinstance(runtime_rules, list):
        rules.extend(runtime_rules)

    matched_rules: List[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if not rule_matches(rule, source_path, origin_name, scene):
            continue

        profile = apply_rule_to_profile(profile, rule)
        matched_rules.append(str(rule.get("name", "unnamed_rule")))

    return profile, matched_rules


def build_resolution_filter(profile: Dict[str, object]) -> Optional[str]:
    strategy = str(profile.get("resolution_strategy", "none")).strip().lower()
    value = str(profile.get("resolution_value", "")).strip()

    if not strategy or strategy == "none":
        return None

    if strategy == "fixed" and ":" in value:
        return f"scale={value}"

    if strategy == "fixed_height" and value.isdigit():
        return f"scale=-2:{value}"

    if strategy == "fixed_width" and value.isdigit():
        return f"scale={value}:-2"

    return None


def chinese_numeral_to_int(text: str) -> Optional[int]:
    if not text:
        return None

    # 例如 一二三 这种写法按逐位数字处理。
    if all(ch in CHINESE_NUMBER_MAP for ch in text):
        digits = [str(CHINESE_NUMBER_MAP[ch]) for ch in text]
        return int("".join(digits))

    total = 0
    current = 0
    for ch in text:
        if ch in CHINESE_NUMBER_MAP:
            current = CHINESE_NUMBER_MAP[ch]
            continue

        if ch in CHINESE_UNIT_MAP:
            unit = CHINESE_UNIT_MAP[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
            continue

        return None

    total += current
    return total if total > 0 else None


def iter_video_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def parse_episode_no(stem: str) -> Optional[str]:
    numeric_patterns = [
        re.compile(r"(?:第)?(\d{1,4})(?:集|话)"),
        re.compile(r"(\d{1,4})$"),
        re.compile(r"(\d{1,4})(?!.*\d)"),
    ]
    for pattern in numeric_patterns:
        match = pattern.search(stem)
        if match:
            return match.group(1).zfill(3)

    chinese_patterns = [
        re.compile(r"第([零〇一二两三四五六七八九十百千]{1,8})(?:集|话)"),
        re.compile(r"([零〇一二两三四五六七八九十百千]{1,8})(?:集|话)"),
    ]
    for pattern in chinese_patterns:
        match = pattern.search(stem)
        if not match:
            continue
        num = chinese_numeral_to_int(match.group(1))
        if num and 1 <= num <= 9999:
            return str(num).zfill(3)

    return None


def derive_series_name_from_stem(stem: str, parent_series_name: str) -> str:
    cleaned = stem
    cleaned = re.sub(r"(?:第)?\d{1,4}(?:集|话)", "", cleaned)
    cleaned = re.sub(r"(?:第)?[零〇一二两三四五六七八九十百千]{1,8}(?:集|话)", "", cleaned)
    cleaned = re.sub(r"\d{1,4}$", "", cleaned)
    cleaned = re.sub(r"[\s_\-\.\(\)\[\]【】（）]+", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned if cleaned else parent_series_name


def series_initials(series_name: str) -> str:
    raw = "".join(lazy_pinyin(series_name, style=Style.FIRST_LETTER, errors="default"))
    raw = re.sub(r"[^0-9a-zA-Z]", "", raw)
    raw = raw.lower()
    return raw or "video"


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


def decode_process_output(raw: bytes) -> str:
    if not raw:
        return ""

    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="replace")


def summarize_ffmpeg_error(stderr_text: str, returncode: int) -> str:
    lines = [line.strip() for line in stderr_text.splitlines() if line.strip()]
    if not lines:
        return f"ffmpeg返回码={returncode}，无可读输出"

    keywords = (
        "error",
        "invalid",
        "not found",
        "no such file",
        "failed",
        "unknown",
    )
    relevant = [line for line in lines if any(key in line.lower() for key in keywords)]
    if relevant:
        return " | ".join(relevant[-3:])

    return lines[-1]


def is_hardware_profile(profile: Dict[str, object]) -> bool:
    hwaccel = str(profile.get("hwaccel", "")).strip()
    codec = str(profile.get("video_codec", "")).strip().lower()
    return bool(hwaccel) or codec in HARDWARE_VIDEO_CODECS


def should_retry_with_cpu(profile: Dict[str, object], stderr_text: str) -> bool:
    if not is_hardware_profile(profile):
        return False

    lower_text = stderr_text.lower()
    return any(keyword in lower_text for keyword in HARDWARE_ERROR_KEYWORDS)


def build_cpu_fallback_profile(profile: Dict[str, object]) -> Dict[str, object]:
    fallback = normalize_profile(profile)
    fallback["hwaccel"] = ""
    fallback["video_codec"] = "libx264"
    return normalize_profile(fallback)


def decode_attempt_outputs(stderr_bytes: bytes, stdout_bytes: bytes) -> str:
    stderr_text = decode_process_output(stderr_bytes)
    if not stderr_text:
        stderr_text = decode_process_output(stdout_bytes)
    return stderr_text


def format_seconds(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def probe_duration_seconds(source_path: Path) -> Optional[float]:
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(source_path),
    ]

    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=False)
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    output = decode_process_output(result.stdout or b"").strip()
    if not output:
        return None

    try:
        duration = float(output)
    except ValueError:
        return None

    return duration if duration > 0 else None


def render_progress_line(prefix: str, detail: str, last_width: int) -> int:
    line = f"{prefix} | {detail}"
    padding = max(0, last_width - len(line))
    sys.stdout.write("\r" + line + (" " * padding))
    sys.stdout.flush()
    return len(line)


def finish_progress_line(message: str, last_width: int) -> None:
    padding = max(0, last_width - len(message))
    sys.stdout.write("\r" + message + (" " * padding) + "\n")
    sys.stdout.flush()


def run_ffmpeg_attempt(
    cmd: List[str],
    duration_seconds: Optional[float],
    progress_prefix: str,
    interactive_progress: bool,
    start_detail: str,
) -> Tuple[int, float, int, bytes, bytes]:
    last_width = 0
    if interactive_progress:
        last_width = render_progress_line(progress_prefix, start_detail, 0)

    run_cmd = [cmd[0], "-progress", "pipe:1", "-nostats", "-v", "error", *cmd[1:]]
    process = subprocess.Popen(run_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    out_time_seconds = 0.0
    while True:
        if process.stdout is None:
            break
        raw_line = process.stdout.readline()
        if not raw_line:
            if process.poll() is not None:
                break
            continue

        line = decode_process_output(raw_line).strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        if key != "out_time_ms":
            continue

        try:
            out_time_seconds = int(value) / 1_000_000
        except ValueError:
            continue

        if interactive_progress:
            if duration_seconds:
                percent = min(100.0, (out_time_seconds / duration_seconds) * 100)
                detail = f"{percent:6.2f}% | {format_seconds(out_time_seconds)}/{format_seconds(duration_seconds)}"
            else:
                detail = f"{format_seconds(out_time_seconds)}"
            last_width = render_progress_line(progress_prefix, detail, last_width)

    returncode = process.wait()
    stderr_bytes = b""
    stdout_bytes = b""
    if process.stderr is not None:
        stderr_bytes = process.stderr.read() or b""
    if process.stdout is not None:
        stdout_bytes = process.stdout.read() or b""

    return returncode, out_time_seconds, last_width, stderr_bytes, stdout_bytes


def process_video(
    source_path: Path,
    scene: Scene,
    record_map: Dict[str, str],
    logger: logging.Logger,
    stats: Dict[str, int],
    file_index: int,
    file_total: int,
) -> None:
    stats["scanned"] += 1
    scene_text = scene_label(scene.name)

    origin_name = source_path.stem
    parent_series_name = normalize_series_name(source_path.parent.name)
    episode_no = parse_episode_no(origin_name)
    if not episode_no:
        stats["skipped"] += 1
        logger.warning(
            "跳过 | %s | 未识别集数 | %s",
            scene_text,
            display_path(source_path),
        )
        return

    series_name_for_output = derive_series_name_from_stem(origin_name, parent_series_name)
    output_name = f"{series_initials(series_name_for_output)}{episode_no}.ts"
    target_path = source_path.parent / output_name

    if target_path.exists():
        stats["skipped"] += 1
        logger.info(
            "跳过 | %s | 目标已存在 | %s",
            scene_text,
            display_path(target_path),
        )
        return

    record_no: Optional[str] = None
    if scene.need_record:
        record_no = record_map.get(parent_series_name)
        if not record_no:
            stats["skipped"] += 1
            logger.error(
                "跳过 | %s | 未找到备案号 | 剧集=%s | 文件=%s",
                scene_text,
                parent_series_name,
                display_path(source_path),
            )
            return

    effective_profile, matched_rules = resolve_effective_profile(scene, source_path, origin_name)
    initial_hwaccel = str(effective_profile.get("hwaccel", "")).strip() or "-"
    initial_codec = str(effective_profile.get("video_codec", "")).strip() or "-"
    logger.info(
        "尝试 | %s | %d/%d | 编码器=%s | 硬件加速=%s | 文件=%s",
        scene_text,
        file_index,
        file_total,
        initial_codec,
        initial_hwaccel,
        source_path.name,
    )

    cmd = build_ffmpeg_command(
        source_path=source_path,
        target_path=target_path,
        profile=effective_profile,
        record_no=record_no,
        origin_name=origin_name,
    )

    duration_seconds = probe_duration_seconds(source_path)
    progress_prefix = f"[{file_index}/{file_total}] 处理中 | {scene_text} | {source_path.name} -> {target_path.name}"
    interactive_progress = sys.stdout.isatty()
    retried_with_cpu = False

    returncode, out_time_seconds, last_width, stderr_bytes, stdout_bytes = run_ffmpeg_attempt(
        cmd=cmd,
        duration_seconds=duration_seconds,
        progress_prefix=progress_prefix,
        interactive_progress=interactive_progress,
        start_detail="准备中...",
    )
    stderr_text = decode_attempt_outputs(stderr_bytes, stdout_bytes)

    if returncode != 0 and should_retry_with_cpu(effective_profile, stderr_text):
        retried_with_cpu = True
        fallback_profile = build_cpu_fallback_profile(effective_profile)
        fallback_hwaccel = str(fallback_profile.get("hwaccel", "")).strip() or "-"
        fallback_codec = str(fallback_profile.get("video_codec", "")).strip() or "-"
        fallback_cmd = build_ffmpeg_command(
            source_path=source_path,
            target_path=target_path,
            profile=fallback_profile,
            record_no=record_no,
            origin_name=origin_name,
        )

        first_error = summarize_ffmpeg_error(stderr_text, returncode)
        if interactive_progress:
            finish_progress_line(
                f"[{file_index}/{file_total}] 硬件失败，回退CPU重试 | {scene_text} | 错误={first_error}",
                last_width,
            )
        else:
            logger.warning(
                "硬件加速失败，回退CPU重试 | %s | %d/%d | %s | 错误=%s",
                scene_text,
                file_index,
                file_total,
                source_path.name,
                first_error,
            )

        logger.info(
            "重试 | %s | %d/%d | 编码器=%s | 硬件加速=%s | 文件=%s",
            scene_text,
            file_index,
            file_total,
            fallback_codec,
            fallback_hwaccel,
            source_path.name,
        )

        returncode, out_time_seconds, last_width, stderr_bytes, stdout_bytes = run_ffmpeg_attempt(
            cmd=fallback_cmd,
            duration_seconds=duration_seconds,
            progress_prefix=progress_prefix,
            interactive_progress=interactive_progress,
            start_detail="CPU重试中...",
        )
        stderr_text = decode_attempt_outputs(stderr_bytes, stdout_bytes)

    if returncode == 0:
        stats["success"] += 1
        retry_note = " | CPU回退" if retried_with_cpu else ""

        if interactive_progress:
            if duration_seconds:
                success_detail = f"100.00% | {format_seconds(duration_seconds)}/{format_seconds(duration_seconds)}"
            else:
                success_detail = f"{format_seconds(out_time_seconds)}"
            finish_progress_line(
                f"[{file_index}/{file_total}] 成功{retry_note} | {scene_text} | {target_path.name} | {success_detail}",
                last_width,
            )
        else:
            logger.info(
                "成功%s | %s | %d/%d | %s -> %s",
                retry_note,
                scene_text,
                file_index,
                file_total,
                source_path.name,
                target_path.name,
            )

        logger.debug(
            "success_detail | scene=%s | profile=%s | rules=%s | retry_cpu=%s | index=%d/%d | source=%s | target=%s",
            scene.name,
            scene.profile_name,
            ",".join(matched_rules) if matched_rules else "-",
            retried_with_cpu,
            file_index,
            file_total,
            display_path(source_path),
            display_path(target_path),
        )
        return

    stats["failed"] += 1
    stderr = stderr_text.strip().replace("\n", " | ")
    summary_error = summarize_ffmpeg_error(stderr_text, returncode)

    if interactive_progress:
        finish_progress_line(
            f"[{file_index}/{file_total}] 失败 | {scene_text} | {source_path.name} -> {target_path.name} | 错误={summary_error}",
            last_width,
        )
    else:
        logger.error(
            "失败 | %s | %d/%d | %s -> %s | 错误=%s",
            scene_text,
            file_index,
            file_total,
            source_path.name,
            target_path.name,
            summary_error,
        )

    logger.debug(
        "failed_detail | scene=%s | profile=%s | rules=%s | retry_cpu=%s | index=%d/%d | source=%s | target=%s | stderr=%s",
        scene.name,
        scene.profile_name,
        ",".join(matched_rules) if matched_rules else "-",
        retried_with_cpu,
        file_index,
        file_total,
        display_path(source_path),
        display_path(target_path),
        stderr,
    )
