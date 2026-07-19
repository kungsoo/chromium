#!/usr/bin/env python3
# Copyright (c) 2026 Alex313031 and gz83.
"""Refresh derived GRD rebase config from the current patch series.

This script intentionally updates only configuration that can be derived from
patch structure:

* feature_patch_message_ownership.csv
* file_allowlist.csv

Reviewed message exceptions and external XTB additions remain manually owned.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]

GRD_SUFFIXES = (".grd", ".grdp")
MESSAGE_RE = re.compile(r"<message\b[^>]*\bname=['\"]([^'\"]+)['\"]")
DIFF_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
SERIES_CONDITION_RE = re.compile(r"^\[[^\]]+\]\s+")


@dataclass(frozen=True, order=True)
class PatchFileChange:
    patch_path: str
    chromium_path: str
    message_ids: tuple[str, ...]


def normalize_path(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def parse_series(series_path: Path) -> list[str]:
    patch_paths: list[str] = []
    seen: set[str] = set()
    for raw_line in series_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = SERIES_CONDITION_RE.sub("", line).strip()
        if ":" in line:
            line = line.split(":", 1)[1].strip()
        if not line.endswith(".patch"):
            continue
        patch_path = normalize_path(line)
        if patch_path not in seen:
            patch_paths.append(patch_path)
            seen.add(patch_path)
    return patch_paths


def extract_patch_changes(repo_root: Path, patch_paths: Iterable[str]) -> list[PatchFileChange]:
    changes: list[PatchFileChange] = []
    for patch_path in patch_paths:
        full_path = repo_root / patch_path
        if not full_path.is_file():
            continue
        changes.extend(extract_one_patch(full_path, patch_path))
    return sorted(changes)


def extract_one_patch(full_path: Path, patch_path: str) -> list[PatchFileChange]:
    lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
    changes: list[PatchFileChange] = []
    index = 0
    while index < len(lines):
        match = DIFF_RE.match(lines[index])
        if not match:
            index += 1
            continue
        chromium_path = normalize_path(match.group(2))
        next_index = index + 1
        while next_index < len(lines) and not DIFF_RE.match(lines[next_index]):
            next_index += 1
        if chromium_path.endswith(GRD_SUFFIXES):
            message_ids = extract_message_ids_from_diff(lines[index:next_index])
            changes.append(
                PatchFileChange(
                    patch_path=patch_path,
                    chromium_path=chromium_path,
                    message_ids=tuple(sorted(message_ids)),
                )
            )
        index = next_index
    return changes


def extract_message_ids_from_diff(diff_lines: list[str]) -> set[str]:
    message_ids: set[str] = set()
    current_message_id = ""
    current_message_changed = False
    in_hunk = False

    def flush_current_message() -> None:
        nonlocal current_message_id, current_message_changed
        if current_message_id and current_message_changed:
            message_ids.add(current_message_id)
        current_message_id = ""
        current_message_changed = False

    for line in diff_lines:
        if line.startswith("@@ "):
            flush_current_message()
            current_message_id = ""
            in_hunk = True
            continue
        if not in_hunk or not line:
            continue
        prefix = line[0]
        if prefix not in (" ", "+", "-"):
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        body = line[1:]
        match = MESSAGE_RE.search(body)
        if match:
            flush_current_message()
            current_message_id = match.group(1)
            if prefix in ("+", "-"):
                current_message_changed = True
        elif prefix in ("+", "-") and current_message_id:
            current_message_changed = True

        if "</message>" in body:
            flush_current_message()

    flush_current_message()
    return message_ids


def update_feature_ownership(
    config_dir: Path,
    changes: list[PatchFileChange],
) -> tuple[int, int]:
    path = config_dir / "feature_patch_message_ownership.csv"
    fieldnames, rows = read_csv(path)
    detected_keys = {
        (change.patch_path, change.chromium_path, message_id)
        for change in changes
        for message_id in change.message_ids
    }
    kept_rows: list[dict[str, str]] = []
    existing_keys: set[tuple[str, str, str]] = set()
    removed = 0

    for row in rows:
        patch_path = row.get("patch_path", "").strip()
        chromium_path = row.get("chromium_path", "").strip()
        message_id = row.get("message_id", "").strip()
        if not patch_path.startswith("other/"):
            kept_rows.append(row)
            continue
        key = (patch_path, chromium_path, message_id)
        if key in detected_keys:
            kept_rows.append(row)
            existing_keys.add(key)
            continue
        removed += 1

    added_rows: list[dict[str, str]] = []
    for key in sorted(detected_keys - existing_keys):
        patch_path, chromium_path, message_id = key
        added_rows.append(
            {
                "patch_path": patch_path,
                "chromium_path": chromium_path,
                "message_id": message_id,
                "ownership": "feature_patch",
                "destination": "keep_in_feature_patch",
                "translation_strategy": "english_source_fallback",
                "notes": (
                    "Auto-detected from current patch series; review "
                    "translation strategy before relying on localized output."
                ),
            }
        )

    merged = sorted(
        kept_rows + added_rows,
        key=lambda row: (
            row.get("patch_path", "").strip(),
            row.get("chromium_path", "").strip(),
            row.get("message_id", "").strip(),
        ),
    )
    write_csv(path, fieldnames, merged)
    return len(added_rows), removed


def update_file_allowlist(
    config_dir: Path,
    changes: list[PatchFileChange],
) -> int:
    path = config_dir / "file_allowlist.csv"
    fieldnames, rows = read_csv(path)
    by_path = {row.get("chromium_path", "").strip(): row for row in rows}
    patch_files = sorted({change.chromium_path for change in changes})
    added = 0

    for chromium_path in patch_files:
        changes_for_file = [change for change in changes if change.chromium_path == chromium_path]
        has_message_change = any(change.message_ids for change in changes_for_file)
        role = "feature_patch_messages" if has_message_change else "structural_resource"
        if chromium_path in by_path:
            row = by_path[chromium_path]
            row["from_patch"] = "True"
            if not row.get("role", "").strip():
                row["role"] = role
            continue
        by_path[chromium_path] = {
            "chromium_path": chromium_path,
            "from_overlay": "False",
            "from_patch": "True",
            "role": role,
            "notes": "Auto-detected from current patch series.",
        }
        added += 1

    existing_paths = {row.get("chromium_path", "").strip() for row in rows}
    merged = rows + [
        by_path[path]
        for path in patch_files
        if path not in existing_paths
    ]
    write_csv(path, fieldnames, merged)
    return added


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update low-risk GRD rebase config from patch series.",
    )
    parser.add_argument("--thorium-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--series",
        type=Path,
        default=REPO_ROOT / "patch_scripts" / "series" / "series",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=REPO_ROOT / "patch_scripts" / "grd_rebase" / "config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write reports only; leave config CSV files unchanged.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    thorium_root = args.thorium_root.resolve()
    config_dir = args.config_dir.resolve()

    patch_paths = parse_series(args.series.resolve())
    changes = extract_patch_changes(thorium_root, patch_paths)

    original_feature = (config_dir / "feature_patch_message_ownership.csv").read_bytes()
    original_file_allowlist = (config_dir / "file_allowlist.csv").read_bytes()

    feature_added, feature_removed = update_feature_ownership(
        config_dir, changes
    )
    file_added = update_file_allowlist(config_dir, changes)

    if args.dry_run:
        (config_dir / "feature_patch_message_ownership.csv").write_bytes(
            original_feature
        )
        (config_dir / "file_allowlist.csv").write_bytes(original_file_allowlist)

    mode = "dry-run" if args.dry_run else "write"
    print(
        f"{mode}: feature ownership +{feature_added}/-{feature_removed}; "
        f"file allowlist +{file_added}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
