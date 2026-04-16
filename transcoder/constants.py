VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".flv", ".wmv", ".m4v", ".ts"}
FONT_PATH = "/System/Library/Fonts/STHeiti Light.ttc"
DEFAULT_RECORD_TABLE_FILENAME = "备案号映射.csv"

SCENE_LABELS = {
    "normal_need_record": "普通需备案号",
    "normal_no_record": "普通不需备案号",
    "jiangsu_need_record": "江苏需备案号",
    "jiangsu_no_record": "江苏不需备案号",
}

# 扩展方式：新增一种命令只需在这里增加 profile，然后在 SCENE_DEFINITIONS 引用它。
# 支持的 profile 字段（均可配置）：
# - hwaccel: 硬件加速名称，如 videotoolbox
# - font_path: drawtext 字体路径
# - video_codec/video_bitrate/fps
# - audio_codec/audio_bitrate/audio_sample_rate
# - add_record_watermark/add_origin_name_watermark
# - resolution_strategy/resolution_value
# - video_filters_base/audio_filters_base
# - extra_output_args: 额外 ffmpeg 输出参数
FFMPEG_PROFILES = {
    "normal_plain": {
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
    },
    "normal_record": {
        "hwaccel": "videotoolbox",
        "font_path": FONT_PATH,
        "video_codec": "h264_videotoolbox",
        "video_bitrate": "8000k",
        "fps": "25",
        "audio_codec": "mp2",
        "audio_bitrate": "192k",
        "audio_sample_rate": "48000",
        "add_record_watermark": True,
        "add_origin_name_watermark": False,
        "resolution_strategy": "none",
        "resolution_value": "",
        "video_filters_base": [],
        "audio_filters_base": [],
        "extra_output_args": [],
    },
    "jiangsu_plain": {
        "hwaccel": "videotoolbox",
        "font_path": FONT_PATH,
        "video_codec": "h264_videotoolbox",
        "video_bitrate": "8000k",
        "fps": "25",
        "audio_codec": "mp2",
        "audio_bitrate": "128k",
        "audio_sample_rate": "48000",
        "add_record_watermark": False,
        "add_origin_name_watermark": True,
        "resolution_strategy": "none",
        "resolution_value": "",
        "video_filters_base": [],
        "audio_filters_base": ["volume=0.5"],
        "extra_output_args": [],
    },
    "jiangsu_record": {
        "hwaccel": "videotoolbox",
        "font_path": FONT_PATH,
        "video_codec": "h264_videotoolbox",
        "video_bitrate": "8000k",
        "fps": "25",
        "audio_codec": "mp2",
        "audio_bitrate": "128k",
        "audio_sample_rate": "48000",
        "add_record_watermark": True,
        "add_origin_name_watermark": True,
        "resolution_strategy": "none",
        "resolution_value": "",
        "video_filters_base": [],
        "audio_filters_base": ["volume=0.5"],
        "extra_output_args": [],
    },
}

# 规则集：按文件名/目录名动态覆盖 profile 字段，或追加滤镜。
# 可按需新增，例如：
# {
#   "name": "preview_720p",
#   "match": {"filename_regex": "预告|trailer"},
#   "overrides": {"resolution_strategy": "fixed_height", "resolution_value": "720"},
#   "append_video_filters": [],
#   "append_audio_filters": []
# }
RULE_SETS = {
    "default": [],
}

SCENE_DEFINITIONS = [
    {
        "name": "normal_need_record",
        "need_record": True,
        "profile_name": "normal_record",
        "rule_set_name": "default",
    },
    {
        "name": "normal_no_record",
        "need_record": False,
        "profile_name": "normal_plain",
        "rule_set_name": "default",
    },
    {
        "name": "jiangsu_need_record",
        "need_record": True,
        "profile_name": "jiangsu_record",
        "rule_set_name": "default",
    },
    {
        "name": "jiangsu_no_record",
        "need_record": False,
        "profile_name": "jiangsu_plain",
        "rule_set_name": "default",
    },
]
