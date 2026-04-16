from dataclasses import dataclass
from pathlib import Path


@dataclass
class Scene:
    name: str
    root: Path
    need_record: bool
    profile_name: str
    rule_set_name: str
