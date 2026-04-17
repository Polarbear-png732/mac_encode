import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple


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
