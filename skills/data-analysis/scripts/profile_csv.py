#!/usr/bin/env python3
"""Safely profile a CSV/TSV file without executing or modifying its contents."""

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
        raise ValueError("input path escapes the approved root")
    if candidate.suffix.lower() not in {".csv", ".tsv"}:
        raise ValueError("only .csv and .tsv inputs are accepted")
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError("input must be a regular, non-symlink file")
    if candidate.stat().st_size > MAX_BYTES:
        raise ValueError(f"input exceeds {MAX_BYTES} bytes")
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
            raise ValueError("input has no header")
        if len(fields) > MAX_COLUMNS:
            raise ValueError(f"input exceeds {MAX_COLUMNS} columns")
        if len(set(fields)) != len(fields):
            raise ValueError("input has duplicate column names")

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
    parser.add_argument("input", help="CSV or TSV path, relative to --root when not absolute")
    parser.add_argument("--root", required=True, help="approved workspace root")
    parser.add_argument("--max-rows", type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.max_rows <= 1_000_000:
        parser.error("--max-rows must be between 1 and 1000000")
    try:
        result = profile(safe_input(args.input, args.root), args.max_rows)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        parser.exit(2, f"profile_csv: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
