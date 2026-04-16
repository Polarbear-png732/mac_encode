import csv
import json
import os
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

import openpyxl

from .constants import DEFAULT_RECORD_TABLE_FILENAME, SCENE_DEFINITIONS, SCENE_LABELS
from .console import ANSI_CYAN, ANSI_DIM, ANSI_GREEN, ANSI_YELLOW, colorize
from .models import Scene


def strip_wrapping_quotes(text: str) -> str:
    result = text.strip()
    pairs = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")}
    while len(result) >= 2 and (result[0], result[-1]) in pairs:
        result = result[1:-1].strip()
    return result


def parse_user_path(raw_value: str, base_dir: Path) -> Path:
    value = strip_wrapping_quotes(raw_value)

    # 支持 file:// 路径输入。
    if value.lower().startswith("file://"):
        parsed = urlparse(value)
        path_text = unquote(parsed.path or "")
        if parsed.netloc:
            path_text = f"//{parsed.netloc}{path_text}"
        if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        value = path_text

    value = os.path.expandvars(value)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def read_config(config_path: Path) -> dict:
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("配置文件格式错误: 顶层必须是对象")

    required_fields = ["log_file", "record_table_path", "roots"]
    for key in required_fields:
        if key not in data:
            raise ValueError(f"配置缺少字段: {key}")

    for key in ("log_file", "record_table_path"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"配置字段 {key} 必须是非空字符串")
        data[key] = str(parse_user_path(value.strip(), config_path.parent))

    if not isinstance(data.get("roots"), dict):
        raise ValueError("配置字段 roots 必须是对象")

    roots = data.get("roots", {})
    normalized_roots = {}
    for name, value in roots.items():
        if value is None:
            normalized_roots[name] = ""
            continue
        if not isinstance(value, str):
            raise ValueError(f"配置字段 roots.{name} 必须是字符串")

        raw_text = value.strip()
        if not raw_text:
            normalized_roots[name] = ""
            continue

        parsed_path = parse_user_path(raw_text, config_path.parent)
        normalized_roots[name] = str(parsed_path)
    data["roots"] = normalized_roots

    if "profile_overrides" in data and not isinstance(data.get("profile_overrides"), dict):
        raise ValueError("配置字段 profile_overrides 必须是对象")

    if "rule_sets" in data and not isinstance(data.get("rule_sets"), dict):
        raise ValueError("配置字段 rule_sets 必须是对象")

    return data


def create_empty_record_table(table_path: Path) -> None:
    table_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = table_path.suffix.lower()

    if suffix == ".csv":
        with table_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["剧集名称", "备案号"])
        return

    if suffix in {".xlsx", ".xlsm"}:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["剧集名称", "备案号"])
        wb.save(table_path)
        wb.close()
        return

    raise ValueError("备案号映射文件扩展名仅支持 csv/xlsx/xlsm")


def create_first_run_files(config_path: Path) -> Tuple[Path, Optional[Path], Path]:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    record_table_path = config_path.parent / DEFAULT_RECORD_TABLE_FILENAME

    config_data = {
        "log_file": "transcode.log",
        "record_table_path": DEFAULT_RECORD_TABLE_FILENAME,
        "roots": {
            "normal_need_record": "",
            "normal_no_record": "",
            "jiangsu_need_record": "",
            "jiangsu_no_record": "",
        },
        "profile_overrides": {},
        "rule_sets": {},
    }

    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    created_record_table: Optional[Path] = None
    if not record_table_path.exists():
        create_empty_record_table(record_table_path)
        created_record_table = record_table_path

    return config_path, created_record_table, record_table_path


def interactive_fill_roots(config_path: Path) -> bool:
    try:
        with config_path.open("r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception:
        return False

    if not isinstance(config_data, dict):
        return False

    roots = config_data.get("roots", {})
    if not isinstance(roots, dict):
        roots = {}

    changed = False
    print("\n现在开始交互填写场景目录（直接回车表示跳过该项）：")
    for scene_def in SCENE_DEFINITIONS:
        scene_name = scene_def["name"]
        scene_text = SCENE_LABELS.get(scene_name, scene_name)
        current_value = str(roots.get(scene_name, "")).strip()
        current_text = current_value if current_value else "未设置"

        print(f"\n- {scene_text} ({scene_name})")
        print(f"  当前值: {current_text}")
        print("  支持示例: D:\\videos\\demo, \"D:\\videos\\demo\", %USERPROFILE%\\Videos, ./demo_input")

        while True:
            try:
                user_input = input("  请输入目录路径（回车跳过）: ").strip()
            except EOFError:
                user_input = ""

            if not user_input:
                break

            input_path = parse_user_path(user_input, config_path.parent)

            if input_path.exists() and input_path.is_file():
                print(f"  检测到文件路径，自动使用其所在目录: {input_path.parent}")
                input_path = input_path.parent

            if not input_path.exists() or not input_path.is_dir():
                print("  路径无效：目录不存在或不是文件夹，请重新输入。")
                continue

            normalized_value = str(input_path)
            if roots.get(scene_name) != normalized_value:
                roots[scene_name] = normalized_value
                changed = True
            break

    config_data["roots"] = roots
    if changed:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            f.write("\n")

    return changed


def wait_for_user_confirmation(config_path: Path) -> None:
    divider = "=" * 64
    print(colorize(divider, ANSI_DIM, stream=None))
    print(colorize("视频转码工具启动提示", ANSI_CYAN, stream=None))
    print(colorize("- 启动后按回车进入交互菜单", ANSI_GREEN, stream=None))
    print(colorize("- 菜单: 1-4 单场景处理, 5 全部处理, 6 修改目录配置, 7 查看配置", ANSI_GREEN, stream=None))
    print(colorize("- 输入 exit 退出程序，按 Ctrl+C 可立即中断", ANSI_YELLOW, stream=None))
    print(colorize(divider, ANSI_DIM, stream=None))

    try:
        input("按回车键开始处理... ")
    except EOFError:
        # 在无交互环境中继续执行，避免因 input 阻塞或报错。
        pass


def build_scenes(config: dict) -> List[Scene]:
    roots = config.get("roots", {})

    scenes: List[Scene] = []
    for scene_def in SCENE_DEFINITIONS:
        name = scene_def["name"]
        need_record = scene_def["need_record"]
        profile_name = scene_def["profile_name"]
        rule_set_name = scene_def.get("rule_set_name", "default")
        root = roots.get(name)
        if not root:
            continue
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            raise FileNotFoundError(f"场景目录不存在或非目录: {name} -> {root_path}")
        scenes.append(
            Scene(
                name=name,
                root=root_path,
                need_record=need_record,
                profile_name=profile_name,
                rule_set_name=rule_set_name,
            )
        )

    if not scenes:
        raise ValueError("roots 至少需要配置一个有效目录")

    return scenes
