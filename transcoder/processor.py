import logging
import sys
from pathlib import Path
from typing import Dict, Iterable

from .constants import VIDEO_EXTENSIONS
from .ffmpeg_command import build_ffmpeg_command
from .ffmpeg_exec import (
    decode_attempt_outputs,
    finish_progress_line,
    format_seconds,
    probe_duration_seconds,
    run_ffmpeg_attempt,
    summarize_ffmpeg_error,
)
from .models import Scene
from .naming import derive_series_name_from_stem, parse_episode_no, series_initials
from .profile_engine import (
    build_cpu_fallback_profile,
    resolve_effective_profile,
    set_runtime_customization,
    should_retry_with_cpu,
)
from .records import normalize_series_name
from .runtime import display_path, scene_label


def iter_video_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


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
        logger.debug(
            "跳过 | %s | 目标已存在 | %s",
            scene_text,
            display_path(target_path),
        )
        return

    record_no = None
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
        "处理参数 | %s | %d/%d | 编码器=%s | 硬件加速=%s | 文件=%s",
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
            logger.debug(
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