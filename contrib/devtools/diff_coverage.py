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


def repo_root() -> Path:
    return Path(run(["git", "rev-parse", "--show-toplevel"]).strip())


def tracked_files() -> tuple[set[str], dict[str, str | None]]:
    return set(run(["git", "ls-files"]).splitlines())


def normalize_path(path_str: str, root: Path, exact: set[str]) -> str | None:
    path = Path(path_str)
    candidate = os.fspath(path.relative_to(root))
    if candidate in exact:
        return candidate
    return None


def changed_lines(base: str) -> dict[str, set[int]]:
    diff = run(["git", "diff", "--unified=0", f"{base}...HEAD", "--"])
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if current_file == "/dev/null":
                current_file = None
            continue
        if current_file is None:
            continue
        match = hunk_re.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count > 0:
            changed.setdefault(current_file, set()).update(range(start, start + count))

    return changed


def file_line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


# https://github.com/llvm/llvm-project/blob/e3574d46e0de8d2c96beb0d092812a3cab153db7/llvm/tools/llvm-cov/CoverageExporterJson.cpp
def coverage_by_file(json_path: Path, root: Path, exact: set[str]) -> dict[str, dict[int, bool]]:
    exported = json.loads(json_path.read_text())
    result: dict[str, dict[int, bool]] = {}

    for entry in exported.get("data", []):
        for file_entry in entry.get("files", []):
            filename = normalize_path(file_entry["filename"], root, exact)
            if filename is None:
                continue

            source_path = root / filename
            last_line = file_line_count(source_path) if source_path.exists() else 0
            if last_line == 0:
                continue

            line_coverage: dict[int, bool] = {}
            segments = file_entry.get("segments", [])

            for index, segment in enumerate(segments):
                line, _col, count, has_count, _is_region_entry, is_gap_region = segment
                if not has_count or is_gap_region:
                    continue
                start = int(line)
                if index + 1 < len(segments):
                    stop = max(start, int(segments[index + 1][0]) - 1)
                else:
                    stop = last_line
                covered = int(count) > 0
                for lineno in range(start, stop + 1):
                    line_coverage[lineno] = line_coverage.get(lineno, False) or covered

            result[filename] = line_coverage

    return result


def summarize(changed: dict[str, set[int]], covered: dict[str, dict[int, bool]]) -> tuple[str, list[str]]:
    details: list[str] = []
    total_relevant = 0
    total_covered = 0

    for filename in sorted(changed):
        file_coverage = covered.get(filename, {})
        relevant = sorted(lineno for lineno in changed[filename] if lineno in file_coverage)
        if not relevant:
            continue

        uncovered = [lineno for lineno in relevant if not file_coverage[lineno]]
        covered_count = len(relevant) - len(uncovered)
        total_relevant += len(relevant)
        total_covered += covered_count

        summary = f"- `{filename}`: {covered_count}/{len(relevant)} changed executable lines covered"
        if uncovered:
            summary += f"; uncovered lines: {', '.join(str(line) for line in uncovered)}"
        details.append(summary)

    if total_relevant == 0:
        return "No changed executable lines found in the diff.", details
    return f"Changed executable lines covered: {total_covered}/{total_relevant}", details


def markdown(summary: str, details: list[str]) -> str:
    body = [COMMENT_MARKER, "## Diff Coverage", "", summary]
    if details:
        body.extend(["", *details])
    body.append("")
    return "\n".join(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-json", required=True, type=Path)
    parser.add_argument("--base", required=True, help="Diff base ref, e.g. origin/master")
    parser.add_argument("--comment-file", type=Path, help="Optional markdown output for a PR comment")
    args = parser.parse_args()

    root = repo_root()
    exact = tracked_files()
    summary, details = summarize(
        changed_lines(args.base),
        coverage_by_file(args.coverage_json.resolve(), root, exact),
    )

    print(summary)
    for line in details:
        print(line)

    output = markdown(summary, details) + "\n"

    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write(output)

    if args.comment_file:
        args.comment_file.write_text(output, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
