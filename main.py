import argparse
from pathlib import Path
from typing import Dict, List

from transcoder.config import (
	build_scenes,
	create_empty_record_table,
	create_first_run_files,
	interactive_fill_roots,
	read_config,
	wait_for_user_confirmation,
)
from transcoder.console import ANSI_CYAN, ANSI_GREEN, ANSI_RED, ANSI_YELLOW, colorize
from transcoder.logging_utils import setup_logger
from transcoder.processor import iter_video_files, process_video, set_runtime_customization
from transcoder.records import read_record_table
from transcoder.runtime import display_path, resolve_runtime_path, scene_label


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


def main() -> int:
	parser = argparse.ArgumentParser(description="按场景批量转码视频")
	parser.add_argument("--config", default="config.json", help="配置文件路径（JSON）")
	args = parser.parse_args()

	config_path = resolve_runtime_path(Path(args.config))
	wait_for_user_confirmation(config_path)

	if not config_path.exists():
		try:
			created_config, created_table, record_table_path = create_first_run_files(config_path)
		except Exception as exc:
			print(f"启动失败: 自动创建初始化文件失败: {exc}")
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
		return 0

	try:
		config = read_config(config_path)
	except Exception as exc:
		print(f"启动失败: {exc}")
		return 1

	set_runtime_customization(
		profile_overrides=config.get("profile_overrides", {}),
		rule_sets=config.get("rule_sets", {}),
	)

	log_path = resolve_runtime_path(Path(config["log_file"]))
	logger = setup_logger(log_path)

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
		print("\n" + colorize("请选择处理模式：", ANSI_CYAN))
		for idx, scene_name in menu_map.items():
			if scene_name in scene_lookup:
				status_text = f"已配置 ({display_path(scene_lookup[scene_name].root)})"
				line_color = ANSI_GREEN
			else:
				status_text = "未配置"
				line_color = ANSI_YELLOW
			print(colorize(f"{idx}. {scene_label(scene_name)} - {status_text}", line_color))
		print(colorize("5. 全部处理（仅处理已配置场景）", ANSI_GREEN))
		print(colorize("6. 修改目录配置（交互填写）", ANSI_CYAN))
		print(colorize("7. 查看当前配置摘要", ANSI_CYAN))
		print(colorize("输入 exit 退出", ANSI_YELLOW))

		try:
			choice = input(colorize("请输入选项: ", ANSI_CYAN)).strip().lower()
		except EOFError:
			logger.info("输入流结束，退出处理循环。")
			break

		if choice == "exit":
			logger.info("已退出处理循环。")
			break

		if choice not in {"1", "2", "3", "4", "5", "6", "7"}:
			logger.warning("无效选项：%s，请输入 1/2/3/4/5/6/7 或 exit", choice)
			continue

		if choice == "7":
			print_config_summary(
				config_path=config_path,
				config=config,
				menu_map=menu_map,
				record_table_path=record_table_path,
				log_path=log_path,
			)
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
				continue

			set_runtime_customization(
				profile_overrides=config.get("profile_overrides", {}),
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
					continue
				logger.info("已自动创建空备案号映射表 | %s", display_path(record_table_path))

			try:
				scenes = build_scenes(config)
				logger.info("场景重载完成 | 场景=%d", len(scenes))
			except Exception as exc:
				logger.warning("场景重载失败，可继续使用菜单 6 修改目录: %s", exc)
				scenes = []

			scene_lookup = {scene.name: scene for scene in scenes}
			continue

		try:
			record_map = read_record_table(record_table_path)
		except Exception as exc:
			logger.error("读取备案号映射失败: %s", exc)
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