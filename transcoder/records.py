import csv
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import openpyxl


def normalize_series_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\s+", " ", name)
    return name


def read_record_table(table_path: Path) -> Dict[str, str]:
    if not table_path.exists():
        raise FileNotFoundError(f"备案号映射文件不存在: {table_path}")

    suffix = table_path.suffix.lower()
    mapping: Dict[str, str] = {}

    if suffix == ".csv":
        rows = _read_rows_from_csv(table_path)
    elif suffix in {".xlsx", ".xlsm"}:
        rows = _read_rows_from_xlsx(table_path)
    else:
        raise ValueError("备案号映射文件仅支持 csv/xlsx/xlsm")

    for idx, row in enumerate(rows, start=1):
        if len(row) < 2:
            continue
        raw_name = str(row[0]).strip() if row[0] is not None else ""
        raw_record_no = str(row[1]).strip() if row[1] is not None else ""
        if not raw_name or not raw_record_no:
            continue

        if idx == 1 and ("剧集" in raw_name and "备案" in raw_record_no):
            continue

        series_name = normalize_series_name(raw_name)
        if not series_name:
            continue
        if series_name in mapping:
            continue
        mapping[series_name] = raw_record_no

    return mapping


def _read_rows_from_csv(table_path: Path) -> Iterable[List[str]]:
    with table_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            yield row


def _read_rows_from_xlsx(table_path: Path) -> Iterable[Tuple[Optional[str], Optional[str]]]:
    wb = openpyxl.load_workbook(table_path, read_only=True, data_only=True)
    ws = wb.active
    try:
        for row in ws.iter_rows(values_only=True):
            yield (row[0] if len(row) > 0 else None, row[1] if len(row) > 1 else None)
    finally:
        wb.close()
