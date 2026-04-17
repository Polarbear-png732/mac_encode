import re
from typing import Optional

from pypinyin import Style, lazy_pinyin


CHINESE_NUMBER_MAP = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNIT_MAP = {
    "十": 10,
    "百": 100,
    "千": 1000,
}


def chinese_numeral_to_int(text: str) -> Optional[int]:
    if not text:
        return None

    if all(ch in CHINESE_NUMBER_MAP for ch in text):
        digits = [str(CHINESE_NUMBER_MAP[ch]) for ch in text]
        return int("".join(digits))

    total = 0
    current = 0
    for ch in text:
        if ch in CHINESE_NUMBER_MAP:
            current = CHINESE_NUMBER_MAP[ch]
            continue

        if ch in CHINESE_UNIT_MAP:
            unit = CHINESE_UNIT_MAP[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
            continue

        return None

    total += current
    return total if total > 0 else None


def parse_episode_no(stem: str) -> Optional[str]:
    numeric_patterns = [
        re.compile(r"(?:第)?(\d{1,4})(?:集|话)"),
        re.compile(r"(\d{1,4})$"),
        re.compile(r"(\d{1,4})(?!.*\d)"),
    ]
    for pattern in numeric_patterns:
        match = pattern.search(stem)
        if match:
            return match.group(1).zfill(3)

    chinese_patterns = [
        re.compile(r"第([零〇一二两三四五六七八九十百千]{1,8})(?:集|话)"),
        re.compile(r"([零〇一二两三四五六七八九十百千]{1,8})(?:集|话)"),
    ]
    for pattern in chinese_patterns:
        match = pattern.search(stem)
        if not match:
            continue
        num = chinese_numeral_to_int(match.group(1))
        if num and 1 <= num <= 9999:
            return str(num).zfill(3)

    return None


def derive_series_name_from_stem(stem: str, parent_series_name: str) -> str:
    cleaned = stem
    cleaned = re.sub(r"(?:第)?\d{1,4}(?:集|话)", "", cleaned)
    cleaned = re.sub(r"(?:第)?[零〇一二两三四五六七八九十百千]{1,8}(?:集|话)", "", cleaned)
    cleaned = re.sub(r"\d{1,4}$", "", cleaned)
    cleaned = re.sub(r"[\s_\-\.\(\)\[\]【】（）]+", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned if cleaned else parent_series_name


def series_initials(series_name: str) -> str:
    raw = "".join(lazy_pinyin(series_name, style=Style.FIRST_LETTER, errors="default"))
    raw = re.sub(r"[^0-9a-zA-Z]", "", raw)
    raw = raw.lower()
    return raw or "video"
