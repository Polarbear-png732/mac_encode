import re
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .constants import FFMPEG_PROFILES, FONT_PATH, RULE_SETS
from .models import Scene


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
