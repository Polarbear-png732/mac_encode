import argparse
from copy import deepcopy
import importlib
import platform
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from transcoder.config import (
	build_scenes,
	create_empty_record_table,
	create_first_run_files,
	interactive_fill_roots,
	read_config,
	wait_for_user_confirmation,
)
from transcoder.constants import WINDOWS_PROFILE_OVERRIDES
from transcoder.console import (
	ANSI_BLUE,
	ANSI_BOLD,
	ANSI_CYAN,
	ANSI_GRAY,
	ANSI_GREEN,
	ANSI_RED,
	ANSI_YELLOW,
	colorize,
	ensure_text_output_encoding,
	init_console,
)
from transcoder.logging_utils import setup_logger
from transcoder.processor import iter_video_files, process_video, set_runtime_customization
from transcoder.records import read_record_table
from transcoder.runtime import display_path, resolve_runtime_path, scene_label


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


def render_cli_header(config: dict, menu_map: Dict[str, str]) -> None:
	roots = config.get("roots", {}) if isinstance(config.get("roots", {}), dict) else {}

	print("\n" + colorize("╭──────────────────────────────────────────────────────────────╮", ANSI_CYAN))
	print(
		colorize("│", ANSI_CYAN)
		+ "                "
		+ colorize("视频转码自动化工具  v1.0.0", ANSI_BOLD)
		+ "                    "
		+ colorize("│", ANSI_CYAN)
	)
	print(colorize("╰──────────────────────────────────────────────────────────────╯", ANSI_CYAN))

	print("\n " + colorize("📂 当前配置状态:", ANSI_BOLD))
	print(" " + colorize("--------------------------------------------------------------", ANSI_GRAY))
	print("  场景类型               状态                 目录路径")
	print(" " + colorize("--------------------------------------------------------------", ANSI_GRAY))

	ready_count = 0
	for idx, scene_name in menu_map.items():
		root_text = str(roots.get(scene_name, "")).strip()
		if not root_text:
			status_text = colorize("[未配置]", ANSI_YELLOW)
			path_text = "--"
		else:
			root_path = Path(root_text)
			if root_path.exists() and root_path.is_dir():
				status_text = colorize("[已就绪]", ANSI_GREEN)
				path_text = display_path(root_path)
				ready_count += 1
			else:
				status_text = colorize("[路径无效]", ANSI_RED)
				path_text = root_text

		print(f"  {idx}. {scene_label(scene_name):<18} {status_text:<22} {colorize(path_text, ANSI_GRAY)}")

	print(" " + colorize("--------------------------------------------------------------", ANSI_GRAY))
	if ready_count == 0:
		print(" " + colorize("⚠ 警告: 尚未配置有效路径，请先执行 [6] 修改目录配置。", ANSI_YELLOW))
	else:
		print(" " + colorize(f"已就绪场景: {ready_count}/{len(menu_map)}", ANSI_GREEN))

	print("\n " + colorize("[Enter] 进入交互菜单 | [Exit] 退出程序 | [Ctrl+C] 中断任务", ANSI_GRAY))


def render_main_menu() -> str:
	print("\n " + colorize("🛠 请选择操作模式:", ANSI_BOLD))
	menu_items = [
		(colorize("[1] 🔹 普通(需备案号)", ANSI_BLUE), colorize("[5] 全部处理 (已配置)", ANSI_GREEN)),
		(colorize("[2] 🔹 普通(不需备案)", ANSI_BLUE), colorize("[6] ⚙ 修改目录配置", ANSI_CYAN)),
		(colorize("[3] 🔸 江苏(需备案号)", ANSI_BLUE), colorize("[7] 📋 查看详细配置", ANSI_CYAN)),
		(colorize("[4] 🔸 江苏(不需备案)", ANSI_BLUE), colorize("[exit] 退出程序", ANSI_RED)),
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


def main() -> int:
	init_console()
	ensure_text_output_encoding()
	session_start = time.time()

	parser = argparse.ArgumentParser(description="按场景批量转码视频")
	parser.add_argument("--config", default="config.json", help="配置文件路径（JSON）")
	args = parser.parse_args()

	config_path = resolve_runtime_path(Path(args.config))
	wait_for_user_confirmation(config_path)

	try:
		ffmpeg_bin, ffprobe_bin = init_ffmpeg_runtime()
	except Exception as exc:
		print(f"启动失败: {exc}")
		print("提示: 首次运行 static-ffmpeg 可能需要联网下载 ffmpeg 二进制。")
		wait_for_menu_continue("初始化失败，按回车退出...")
		return 1

	if not config_path.exists():
		try:
			created_config, created_table, record_table_path = create_first_run_files(config_path)
		except Exception as exc:
			print(f"启动失败: 自动创建初始化文件失败: {exc}")
			wait_for_menu_continue("初始化失败，按回车退出...")
			return 1

		print(f"首次启动，已创建配置文件: {created_config}")
		if created_table:
			print(f"首次启动，已创建空备案号映射表: {created_table}")
		else:
			print(f"检测到已存在备案号映射表（未覆盖）: {record_table_path}")
		roots_saved = interactive_fill_roots(created_config)
		if roots_saved:
			print("目录已写入配置文件。")
		else:
			print("目录未写入（你可以稍后手动编辑配置文件中的 roots）。")

		print("请继续填写备案号映射表后再重新运行：")
		print("1. 打开备案号映射表，按两列填写")
		print("   - 第1列：剧集名称（需与视频所在文件夹名一致）")
		print("   - 第2列：备案号")
		print("   - 示例：果宝特攻, V32012345678901")
		print("2. 保存后重新运行程序。")
		wait_for_menu_continue("初始化完成，按回车退出...")
		return 0

	try:
		config = read_config(config_path)
	except Exception as exc:
		print(f"启动失败: {exc}")
		wait_for_menu_continue("配置读取失败，按回车退出...")
		return 1

	set_runtime_customization(
		profile_overrides=build_effective_profile_overrides(config.get("profile_overrides", {})),
		rule_sets=config.get("rule_sets", {}),
	)

	log_path = resolve_runtime_path(Path(config["log_file"]))
	logger = setup_logger(log_path)
	logger.info("FFmpeg运行环境就绪 | ffmpeg=%s | ffprobe=%s", ffmpeg_bin, ffprobe_bin)

	record_table_path = resolve_runtime_path(Path(config["record_table_path"]))
	if not record_table_path.exists():
		try:
			create_empty_record_table(record_table_path)
		except Exception as exc:
			logger.error("启动失败: 自动创建备案号映射表失败: %s", exc)
			return 1
		logger.info("已自动创建空备案号映射表 | %s", display_path(record_table_path))

	try:
		scenes = build_scenes(config)
	except Exception as exc:
		logger.warning("场景加载失败，可通过菜单 6 重新配置目录: %s", exc)
		scenes = []

	scene_lookup = {scene.name: scene for scene in scenes}
	scene_order = [
		"normal_need_record",
		"normal_no_record",
		"jiangsu_need_record",
		"jiangsu_no_record",
	]
	menu_map = {
		"1": "normal_need_record",
		"2": "normal_no_record",
		"3": "jiangsu_need_record",
		"4": "jiangsu_no_record",
	}

	logger.info("加载完成 | 场景=%d", len(scenes))
	session_stats = {"scanned": 0, "success": 0, "skipped": 0, "failed": 0}

	while True:
		try:
			choice = render_main_menu()
		except KeyboardInterrupt:
			print("\n" + colorize("中断退出...", ANSI_RED))
			break
		except EOFError:
			logger.info("输入流结束，退出处理循环。")
			break

		if choice == "exit":
			logger.info("已退出处理循环。")
			break

		if choice not in {"1", "2", "3", "4", "5", "6", "7"}:
			logger.warning("无效选项：%s，请输入 1/2/3/4/5/6/7 或 exit", choice)
			wait_for_menu_continue()
			continue

		if choice == "7":
			print_config_summary(
				config_path=config_path,
				config=config,
				menu_map=menu_map,
				record_table_path=record_table_path,
				log_path=log_path,
			)
			wait_for_menu_continue()
			continue

		if choice == "6":
			updated = interactive_fill_roots(config_path)
			if updated:
				logger.info("目录配置已更新，正在重载场景。")
			else:
				logger.info("目录配置未变化，正在重载场景。")

			try:
				config = read_config(config_path)
			except Exception as exc:
				logger.error("重载配置失败: %s", exc)
				wait_for_menu_continue()
				continue

			set_runtime_customization(
				profile_overrides=build_effective_profile_overrides(config.get("profile_overrides", {})),
				rule_sets=config.get("rule_sets", {}),
			)

			new_log_path = resolve_runtime_path(Path(config["log_file"]))
			if new_log_path != log_path:
				log_path = new_log_path
				logger = setup_logger(log_path)
				logger.info("日志文件已切换 | %s", display_path(log_path))

			record_table_path = resolve_runtime_path(Path(config["record_table_path"]))
			if not record_table_path.exists():
				try:
					create_empty_record_table(record_table_path)
				except Exception as exc:
					logger.error("重载失败: 自动创建备案号映射表失败: %s", exc)
					wait_for_menu_continue()
					continue
				logger.info("已自动创建空备案号映射表 | %s", display_path(record_table_path))

			try:
				scenes = build_scenes(config)
				logger.info("场景重载完成 | 场景=%d", len(scenes))
			except Exception as exc:
				logger.warning("场景重载失败，可继续使用菜单 6 修改目录: %s", exc)
				scenes = []

			scene_lookup = {scene.name: scene for scene in scenes}
			wait_for_menu_continue()
			continue

		try:
			record_map = read_record_table(record_table_path)
		except Exception as exc:
			logger.error("读取备案号映射失败: %s", exc)
			wait_for_menu_continue()
			continue

		if any(scene.need_record for scene in scenes) and not record_map:
			logger.warning("备案号映射为空：需要备案号的场景将全部被跳过，请先填写映射表。")

		if choice == "5":
			target_names = scene_order
		else:
			target_names = [menu_map[choice]]

		selected_scenes = []
		for name in target_names:
			scene = scene_lookup.get(name)
			if not scene:
				logger.warning("场景未配置，已跳过：%s", scene_label(name))
				continue
			selected_scenes.append(scene)

		if not selected_scenes:
			logger.warning("本轮没有可处理的场景。")
			wait_for_menu_continue()
			continue

		round_stats = {"scanned": 0, "success": 0, "skipped": 0, "failed": 0}
		for scene in selected_scenes:
			logger.info("开始场景 | %s | 根目录=%s", scene_label(scene.name), display_path(scene.root))
			scene_files = list(iter_video_files(scene.root))
			scene_total = len(scene_files)
			for index, source_path in enumerate(scene_files, start=1):
				process_video(
					source_path=source_path,
					scene=scene,
					record_map=record_map,
					logger=logger,
					stats=round_stats,
					file_index=index,
					file_total=scene_total,
				)

		for key in session_stats:
			session_stats[key] += round_stats[key]

		logger.info(
			"本轮完成 | 扫描=%d 成功=%d 跳过=%d 失败=%d",
			round_stats["scanned"],
			round_stats["success"],
			round_stats["skipped"],
			round_stats["failed"],
		)
		wait_for_menu_continue("处理完成，按回车返回菜单...")

	print_session_summary_table(session_stats, elapsed_seconds=int(time.time() - session_start))
	logger.info(
		"会话汇总 | 扫描=%d 成功=%d 跳过=%d 失败=%d",
		session_stats["scanned"],
		session_stats["success"],
		session_stats["skipped"],
		session_stats["failed"],
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())