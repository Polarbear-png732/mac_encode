from copy import deepcopy
import importlib
import platform
import shutil
from typing import Dict, Tuple

from .constants import WINDOWS_PROFILE_OVERRIDES


def build_effective_profile_overrides(user_overrides: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    base: Dict[str, Dict[str, object]] = {}
    if platform.system().lower() == "windows":
        base = deepcopy(WINDOWS_PROFILE_OVERRIDES)

    if not isinstance(user_overrides, dict):
        return base

    for profile_name, override in user_overrides.items():
        if not isinstance(override, dict):
            continue
        current = base.get(profile_name, {})
        if not isinstance(current, dict):
            current = {}
        next_override = deepcopy(current)
        next_override.update(override)
        base[profile_name] = next_override

    return base


def init_ffmpeg_runtime() -> Tuple[str, str]:
    try:
        static_ffmpeg = importlib.import_module("static_ffmpeg")
    except Exception as exc:
        raise RuntimeError(f"未安装 static-ffmpeg: {exc}")

    try:
        static_ffmpeg.add_paths()
    except Exception as exc:
        raise RuntimeError(f"初始化 static-ffmpeg 失败: {exc}")

    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    if not ffmpeg_bin or not ffprobe_bin:
        raise RuntimeError("未找到 ffmpeg 或 ffprobe，可执行文件路径注入失败")

    return ffmpeg_bin, ffprobe_bin
