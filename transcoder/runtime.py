from pathlib import Path

from .constants import SCENE_LABELS


def resolve_runtime_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def scene_label(scene_name: str) -> str:
    return SCENE_LABELS.get(scene_name, scene_name)


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return path.as_posix()
