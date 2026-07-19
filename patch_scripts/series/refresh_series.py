#!/usr/bin/env python3
# Copyright (c) 2026 Alex313031 and gz83.
"""Refresh Thorium patch hunks against the ordered patch series.

The script applies the series to temporary Git indexes only. It never modifies
the Chromium worktree or the Chromium real index. For each selected patch, it
exports the temporary tree delta produced by that single series entry and
compares it with the existing patch file.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

import apply_series


def run_git(
    apply_dir: Path,
    args: list[str],
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(apply_dir), *args],
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def git_text(apply_dir: Path, args: list[str], env: dict[str, str]) -> str:
    result = run_git(apply_dir, args, env)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"git {' '.join(args)} failed in {apply_dir}")
    return result.stdout.strip()


def patch_has_mail_header(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        return line.startswith("From ") or line.startswith("Subject:")
    return False


def patch_diff(apply_dir: Path, before_tree: str, after_tree: str, env: dict[str, str]) -> str:
    result = run_git(
        apply_dir,
        [
            "diff",
            "--binary",
            "--relative",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            before_tree,
            after_tree,
        ],
        env,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        raise RuntimeError(f"git diff failed in {apply_dir}")
    return result.stdout


def write_patch(path: Path, diff_text: str) -> None:
    if diff_text and not diff_text.endswith("\n"):
        diff_text += "\n"
    path.write_text(diff_text, encoding="utf-8", newline="\n")


def normalized_patch_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def listed_patch_paths(entries: list[apply_series.SeriesEntry]) -> set[str]:
    return {entry.patch_path.replace("\\", "/") for entry in entries}


def other_patch_paths(thorium_root: Path) -> set[str]:
    return {
        path.relative_to(thorium_root).as_posix()
        for path in (thorium_root / "other").rglob("*.patch")
    }


def refresh_allowed(
    entry: apply_series.SeriesEntry,
    requested_condition: str | None,
    all_conditions: bool,
) -> bool:
    if all_conditions:
        return True
    if requested_condition is None:
        return not entry.conditions
    return requested_condition in entry.conditions


def main(argv: list[str]) -> int:
    default_root = apply_series.default_thorium_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--thorium-root",
        type=Path,
        default=default_root,
        help="Thorium repository root. Defaults to THOR_DIR or this repository.",
    )
    parser.add_argument(
        "--source-tree",
        type=Path,
        default=None,
        help="Chromium source tree. Defaults match apply_series.py.",
    )
    parser.add_argument(
        "--series",
        type=Path,
        default=default_root / "patch_scripts" / "series" / "series",
    )
    parser.add_argument(
        "--condition",
        action="append",
        default=[],
        help="Enable one conditional entry, e.g. raspi or sse2.",
    )
    parser.add_argument(
        "--all-conditions",
        action="store_true",
        help="Refresh every series entry, including all conditional variants.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Overwrite drifted patch files. Dry-run is the default.",
    )
    args = parser.parse_args(argv)
    if len(args.condition) > 1:
        parser.error("only one --condition value is supported per run")
    if args.condition and args.all_conditions:
        parser.error("--condition and --all-conditions cannot be used together")
    if args.all_conditions and args.write:
        parser.error("--all-conditions cannot be combined with --write")

    thorium_root = args.thorium_root.resolve()
    source_tree = (args.source_tree or apply_series.default_source_tree()).resolve()
    series_path = args.series if args.series.is_absolute() else thorium_root / args.series

    all_entries = apply_series.parse_series(series_path)
    unlisted = sorted(other_patch_paths(thorium_root) - listed_patch_paths(all_entries))
    if unlisted:
        for patch_path in unlisted:
            print(f"error: patch is not listed in series: {patch_path}", file=sys.stderr)
        return 2

    requested_condition = args.condition[0].lower() if args.condition else None
    if args.all_conditions:
        entries = all_entries
    elif requested_condition is not None:
        enabled_conditions = {requested_condition}
        entries = [
            entry
            for entry in all_entries
            if not entry.conditions or apply_series.selected(entry, enabled_conditions)
        ]
    else:
        entries = [entry for entry in all_entries if not entry.conditions]

    errors = apply_series.validate_entries(entries, thorium_root, source_tree)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2

    changed = 0
    skipped_headers = 0
    clean = 0
    context_only = 0

    with tempfile.TemporaryDirectory(prefix="thorium-refresh-index-") as temp:
        temp_dir = Path(temp)
        indexes: dict[str, Path] = {}
        envs: dict[Path, dict[str, str]] = {}

        for entry in entries:
            patch = (thorium_root / entry.patch_path).resolve()
            apply_dir = (source_tree / entry.apply_root).resolve()
            label = (
                f"{entry.apply_root}: {entry.patch_path}"
                if entry.apply_root != "."
                else entry.patch_path
            )
            print(f"scan: {label}", flush=True)
            env = apply_series.prepare_temp_index(apply_dir, temp_dir, indexes, envs)
            before_tree = git_text(apply_dir, ["write-tree"], env)

            result = subprocess.run(
                apply_series.git_apply_command(apply_dir, patch, ["--cached"]),
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
            )
            output = f"{result.stdout}{result.stderr}"
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout, end="")
                if result.stderr:
                    print(result.stderr, end="", file=sys.stderr)
                print(f"failed: {label}", file=sys.stderr)
                return 1

            after_tree = git_text(apply_dir, ["write-tree"], env)
            if not refresh_allowed(entry, requested_condition, args.all_conditions):
                context_only += 1
                continue

            if patch_has_mail_header(patch):
                skipped_headers += 1
                print(f"skip mail-style patch: {label}")
                continue

            diff_text = patch_diff(apply_dir, before_tree, after_tree, env)
            if normalized_patch_text(patch) == diff_text:
                clean += 1
                continue

            changed += 1
            action = "update" if args.write else "would update"
            print(f"{action}: {label}")

            if args.write:
                if not diff_text:
                    print(f"error: refreshed diff is empty for {label}", file=sys.stderr)
                    return 1
                write_patch(patch, diff_text)

    print(
        f"summary: {'updated' if args.write else 'would update'} {changed} patch(es); "
        f"{clean} clean; {context_only} context-only; "
        f"{skipped_headers} skipped mail-style patch(es)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
