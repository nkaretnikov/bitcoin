#!/usr/bin/env python3
#
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit.

"""Report coverage for changed lines in a git diff using llvm-cov export JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

COMMENT_MARKER = "<!-- diff-coverage -->"


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def get_repo_root() -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"]).strip())


def build_tracked_file_index(repo_root: Path) -> tuple[set[str], dict[str, str | None]]:
    tracked = run(["git", "ls-files"]).splitlines()
    tracked_set = set(tracked)
    suffix_map: dict[str, str | None] = {}
    for path in tracked:
        parts = Path(path).parts
        for idx in range(len(parts)):
            suffix = os.fspath(Path(*parts[idx:]))
            if suffix in suffix_map and suffix_map[suffix] != path:
                suffix_map[suffix] = None
            else:
                suffix_map.setdefault(suffix, path)
    return tracked_set, suffix_map


def to_repo_relative(path_str: str, repo_root: Path, tracked_set: set[str], suffix_map: dict[str, str | None]) -> str | None:
    path = Path(path_str)
    direct = os.fspath(path)
    if direct in tracked_set:
        return direct
    try:
        rel = os.fspath(path.relative_to(repo_root))
        if rel in tracked_set:
            return rel
    except Exception:
        pass
    candidate = suffix_map.get(direct)
    if candidate:
        return candidate
    parts = path.parts
    for idx in range(len(parts)):
        suffix = os.fspath(Path(*parts[idx:]))
        candidate = suffix_map.get(suffix)
        if candidate:
            return candidate
    return None


def parse_diff(base: str) -> dict[str, set[int]]:
    output = run(["git", "diff", "--unified=0", f"{base}...HEAD", "--"])
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in output.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if current_file == "/dev/null":
                current_file = None
            continue
        if not current_file:
            continue
        match = hunk_re.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count == 0:
            continue
        changed.setdefault(current_file, set()).update(range(start, start + count))
    return changed


def parse_coverage(json_path: Path, repo_root: Path, tracked_set: set[str], suffix_map: dict[str, str | None]) -> dict[str, dict[int, bool]]:
    data = json.loads(json_path.read_text())
    covered_by_file: dict[str, dict[int, bool]] = {}

    for export in data.get("data", []):
        for file_entry in export.get("files", []):
            filename = to_repo_relative(file_entry["filename"], repo_root, tracked_set, suffix_map)
            if not filename:
                continue
            segments = file_entry.get("segments", [])
            line_state: dict[int, bool] = {}
            file_line_count = None
            source_path = repo_root / filename
            if source_path.exists():
                file_line_count = len(source_path.read_text(encoding="utf-8", errors="replace").splitlines()) or 1
            for idx, segment in enumerate(segments):
                line, _col, count, has_count, _is_region_entry, is_gap_region = segment
                if not has_count or is_gap_region:
                    continue
                if idx + 1 < len(segments):
                    next_line = int(segments[idx + 1][0])
                    end_line = max(int(line), next_line - 1)
                else:
                    end_line = file_line_count or int(line)
                start_line = int(line)
                if end_line < start_line:
                    continue
                for lineno in range(start_line, end_line + 1):
                    prev = line_state.get(lineno, False)
                    line_state[lineno] = prev or int(count) > 0
            covered_by_file[filename] = line_state
    return covered_by_file


def summarize(changed: dict[str, set[int]], coverage: dict[str, dict[int, bool]]) -> tuple[list[str], int, int]:
    lines: list[str] = []
    total_relevant = 0
    total_covered = 0

    for filename in sorted(changed):
        file_cov = coverage.get(filename, {})
        rel_name = filename
        uncovered: list[int] = []
        covered_count = 0
        relevant_count = 0

        for lineno in sorted(changed[filename]):
            if lineno not in file_cov:
                continue
            relevant_count += 1
            if file_cov[lineno]:
                covered_count += 1
            else:
                uncovered.append(lineno)

        if relevant_count == 0:
            continue

        total_relevant += relevant_count
        total_covered += covered_count
        if uncovered:
            joined = ", ".join(str(n) for n in uncovered)
            lines.append(f"- `{rel_name}`: {covered_count}/{relevant_count} changed executable lines covered; uncovered lines: {joined}")
        else:
            lines.append(f"- `{rel_name}`: {covered_count}/{relevant_count} changed executable lines covered")

    return lines, total_covered, total_relevant


def build_markdown(summary: str, lines: list[str]) -> str:
    body = [COMMENT_MARKER, "## Diff Coverage", "", summary]
    if lines:
        body.append("")
        body.extend(lines)
    body.append("")
    return "\n".join(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", required=True, type=Path)
    parser.add_argument("--base", required=True, help="Diff base ref, e.g. origin/master")
    parser.add_argument("--comment-file", type=Path, help="Optional markdown output for a PR comment")
    args = parser.parse_args()

    repo_root = get_repo_root()
    tracked_set, suffix_map = build_tracked_file_index(repo_root)
    changed = parse_diff(args.base)
    coverage = parse_coverage(args.coverage_json.resolve(), repo_root, tracked_set, suffix_map)
    lines, covered, relevant = summarize(changed, coverage)

    if relevant == 0:
        summary = "No changed executable lines found in the diff."
    else:
        summary = f"Changed executable lines covered: {covered}/{relevant}"

    print(summary)
    for line in lines:
        print(line)

    markdown = build_markdown(summary, lines)

    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")

    if args.comment_file:
        args.comment_file.write_text(markdown + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
