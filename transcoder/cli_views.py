from pathlib import Path
from typing import Dict, Optional

from .console import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_GRAY,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_YELLOW,
    colorize,
)
from .runtime import scene_label


def print_config_summary(
    config_path: Path,
    config: dict,
    menu_map: Dict[str, str],
    record_table_path: Path,
    log_path: Path,
) -> None:
    def abs_text(path: Path) -> str:
        try:
            return path.resolve().as_posix()
        except Exception:
            return path.as_posix()

    roots = config.get("roots", {}) if isinstance(config.get("roots", {}), dict) else {}

    print("\n" + colorize("当前配置摘要", ANSI_CYAN))
    print(colorize(f"- 配置文件: {abs_text(config_path)}", ANSI_GREEN))
    print(colorize(f"- 日志文件: {abs_text(log_path)}", ANSI_GREEN))
    print(colorize(f"- 备案映射表: {abs_text(record_table_path)}", ANSI_GREEN))

    for idx, scene_name in menu_map.items():
        root_text = str(roots.get(scene_name, "")).strip()
        if not root_text:
            print(colorize(f"{idx}. {scene_label(scene_name)} - 未配置", ANSI_YELLOW))
            continue

        root_path = Path(root_text)
        if root_path.exists() and root_path.is_dir():
            print(colorize(f"{idx}. {scene_label(scene_name)} - {abs_text(root_path)}", ANSI_GREEN))
        else:
            print(colorize(f"{idx}. {scene_label(scene_name)} - 无效路径: {abs_text(root_path)}", ANSI_RED))


def render_main_menu() -> str:
    print("\n " + colorize("🛠 请选择操作模式:", ANSI_BOLD))
    menu_items = [
        (colorize("[1] 🔹 普通(需备案号)", ANSI_BLUE), colorize("[5] 全部处理 (已配置)", ANSI_GREEN)),
        (colorize("[2] 🔹 普通(不需备案号)", ANSI_BLUE), colorize("[6] ⚙ 修改目录配置", ANSI_CYAN)),
        (colorize("[3] 🔸 江苏(需备案号)", ANSI_BLUE), colorize("[7] 📋 查看详细配置", ANSI_CYAN)),
        (colorize("[4] 🔸 江苏(不需备案号)", ANSI_BLUE), colorize("[exit] 退出程序", ANSI_RED)),
    ]

    for left, right in menu_items:
        print(f"  {left:<35} {right}")

    return input("\n " + colorize("💡 请输入选项 (1-7): ", ANSI_YELLOW)).strip().lower()


def wait_for_menu_continue(message: str = "按回车继续...") -> None:
    try:
        input("\n " + colorize(message, ANSI_GRAY))
    except EOFError:
        pass


def print_session_summary_table(stats: Dict[str, int], elapsed_seconds: int) -> None:
    def cell(value: object, width: int, color: Optional[str] = None) -> str:
        text = str(value).ljust(width)
        if color:
            return colorize(text, color)
        return text

    total = max(0, int(elapsed_seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    elapsed_text = f"{h:02d}:{m:02d}:{s:02d}"

    print("\n " + colorize("📊 会话执行汇总", ANSI_BOLD))
    print(" " + colorize("┏━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━━┓", ANSI_BLUE))
    print(" " + colorize("┃ 总扫描   ┃ 成功 ┃ 跳过 ┃ 失败 ┃ 总耗时   ┃", ANSI_BLUE))
    print(" " + colorize("┣━━━━━━━━━━╋━━━━━━╋━━━━━━╋━━━━━━╋━━━━━━━━━━┫", ANSI_BLUE))
    print(
        " " + colorize("┃", ANSI_BLUE) + f" {cell(stats['scanned'], 8)} " + colorize("┃", ANSI_BLUE)
        + f" {cell(stats['success'], 4, ANSI_GREEN)} "
        + colorize("┃", ANSI_BLUE)
        + f" {cell(stats['skipped'], 4, ANSI_YELLOW)} "
        + colorize("┃", ANSI_BLUE)
        + f" {cell(stats['failed'], 4, ANSI_RED)} "
        + colorize("┃", ANSI_BLUE)
        + f" {cell(elapsed_text, 8)} "
        + colorize("┃", ANSI_BLUE)
    )
    print(" " + colorize("┗━━━━━━━━━━┻━━━━━━┻━━━━━━┻━━━━━━┻━━━━━━━━━━┛", ANSI_BLUE))
