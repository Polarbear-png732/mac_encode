import argparse
import time
from pathlib import Path

from transcoder.bootstrap import build_effective_profile_overrides, init_ffmpeg_runtime
from transcoder.cli_views import (
	print_config_summary,
	print_session_summary_table,
	render_main_menu,
	wait_for_menu_continue,
)
from transcoder.config import (
	build_scenes,
	create_empty_record_table,
	create_first_run_files,
	interactive_fill_roots,
	read_config,
	wait_for_user_confirmation,
)
from transcoder.console import ANSI_RED, colorize, ensure_text_output_encoding, init_console
from transcoder.logging_utils import setup_logger
from transcoder.processor import iter_video_files, process_video, set_runtime_customization
from transcoder.records import read_record_table
from transcoder.runtime import display_path, resolve_runtime_path, scene_label


def main() -> int:
	init_console()
	ensure_text_output_encoding()
	session_start = time.time()

	parser = argparse.ArgumentParser(description="按处理模式批量转码视频")
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
		logger.warning("处理模式列表加载失败，可通过菜单 6 重新配置目录: %s", exc)
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

	session_stats = {"scanned": 0, "success": 0, "skipped": 0, "failed": 0}

	while True:
		try:
			choice = render_main_menu()
		except KeyboardInterrupt:
			print("\n" + colorize("中断退出...", ANSI_RED))
			break
		except EOFError:
			break

		if choice == "exit":
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
			old_roots = config.get("roots", {}) if isinstance(config.get("roots", {}), dict) else {}
			old_roots = {str(k): str(v).strip() for k, v in old_roots.items()}
			updated = interactive_fill_roots(config_path)

			try:
				config = read_config(config_path)
			except Exception as exc:
				logger.error("重新读取配置失败: %s", exc)
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
			except Exception as exc:
				logger.warning("处理模式列表加载失败，可继续使用菜单 6 修改目录: %s", exc)
				scenes = []

			if updated:
				new_roots = config.get("roots", {}) if isinstance(config.get("roots", {}), dict) else {}
				changes = []
				for scene_name, raw_path in new_roots.items():
					new_value = str(raw_path).strip()
					old_value = old_roots.get(str(scene_name), "")
					if not new_value or new_value == old_value:
						continue
					changes.append(f"{scene_label(str(scene_name))}={display_path(Path(new_value))}")

				if changes:
					logger.info("目录配置已更新 | %s", " ; ".join(changes))
				else:
					logger.info("目录配置已更新")

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
			logger.warning("备案号映射为空：需要备案号的处理模式将全部被跳过，请先填写映射表。")

		if choice == "5":
			target_names = scene_order
		else:
			target_names = [menu_map[choice]]

		selected_scenes = []
		for name in target_names:
			scene = scene_lookup.get(name)
			if not scene:
				logger.warning("处理模式未配置，已跳过：%s", scene_label(name))
				continue
			selected_scenes.append(scene)

		if not selected_scenes:
			logger.warning("本轮没有可处理的模式。")
			wait_for_menu_continue()
			continue

		round_stats = {"scanned": 0, "success": 0, "skipped": 0, "failed": 0}
		for scene in selected_scenes:
			logger.info("开始处理模式 | %s | 根目录=%s", scene_label(scene.name), display_path(scene.root))
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