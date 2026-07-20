#!/usr/bin/env python3
"""在不执行或修改文件内容的前提下，安全分析 CSV/TSV 文件。"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

MAX_BYTES = 50 * 1024 * 1024
MAX_COLUMNS = 500
MAX_VALUE_LENGTH = 2_000


def safe_input(path_text: str, root_text: str) -> Path:
    root = Path(root_text).expanduser().resolve(strict=True)
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve(strict=True)
    if candidate != root and root not in candidate.parents:
        raise ValueError("输入路径超出已批准的根目录")
    if candidate.suffix.lower() not in {".csv", ".tsv"}:
        raise ValueError("仅接受 .csv 和 .tsv 输入文件")
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("输入必须是普通文件，不能是符号链接")
    if candidate.stat().st_size > MAX_BYTES:
        raise ValueError(f"输入文件超过 {MAX_BYTES} 字节限制")
    return candidate


def as_number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def profile(path: Path, max_rows: int) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = reader.fieldnames or []
        if not fields:
            raise ValueError("输入文件缺少表头")
        if len(fields) > MAX_COLUMNS:
            raise ValueError(f"输入文件超过 {MAX_COLUMNS} 列限制")
        if len(set(fields)) != len(fields):
            raise ValueError("输入文件包含重复列名")

        missing = Counter({field: 0 for field in fields})
        numeric_count = Counter({field: 0 for field in fields})
        numeric_min: dict[str, float] = {}
        numeric_max: dict[str, float] = {}
        distinct: dict[str, set[str]] = {field: set() for field in fields}
        truncated_distinct: set[str] = set()
        rows = 0

        for row in reader:
            if rows >= max_rows:
                break
            rows += 1
            for field in fields:
                raw = row.get(field)
                value = "" if raw is None else raw.strip()
                if not value:
                    missing[field] += 1
                    continue
                if len(value) > MAX_VALUE_LENGTH:
                    value = value[:MAX_VALUE_LENGTH]
                if len(distinct[field]) < 1_001:
                    distinct[field].add(value)
                else:
                    truncated_distinct.add(field)
                number = as_number(value)
                if number is not None:
                    numeric_count[field] += 1
                    numeric_min[field] = min(number, numeric_min.get(field, number))
                    numeric_max[field] = max(number, numeric_max.get(field, number))

    columns = []
    for field in fields:
        non_missing = rows - missing[field]
        numeric = numeric_count[field]
        item: dict[str, Any] = {
            "name": field,
            "missing": missing[field],
            "non_missing": non_missing,
            "distinct": len(distinct[field]),
            "distinct_truncated": field in truncated_distinct,
            "numeric_values": numeric,
            "inferred_type": "number" if non_missing and numeric == non_missing else "text",
        }
        if numeric:
            item["numeric_min"] = numeric_min[field]
            item["numeric_max"] = numeric_max[field]
        columns.append(item)
    return {"file": path.name, "rows_profiled": rows, "columns": columns}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="CSV 或 TSV 路径；相对路径以 --root 为基准")
    parser.add_argument("--root", required=True, help="已批准的工作区根目录")
    parser.add_argument("--max-rows", type=int, default=100_000, help="最多分析的行数")
    args = parser.parse_args()
    if not 1 <= args.max_rows <= 1_000_000:
        parser.error("--max-rows 必须介于 1 和 1000000 之间")
    try:
        result = profile(safe_input(args.input, args.root), args.max_rows)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        parser.exit(2, f"profile_csv：{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
