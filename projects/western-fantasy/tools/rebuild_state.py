"""Rebuild hard state from chapter files."""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_PATH))

from story_state_manager import StoryStateManager


def parse_chapter_num(filename: str) -> int:
    match = re.search(r"第(\d+)章", filename)
    if match:
        return int(match.group(1))
    return -1


def collect_chapters(chapters_dir: Path):
    files = list(chapters_dir.rglob("*.txt"))
    items = []
    for file in files:
        chapter_num = parse_chapter_num(file.name)
        if chapter_num > 0:
            items.append((chapter_num, file))
    return sorted(items, key=lambda x: x[0])


def main():
    parser = argparse.ArgumentParser(description="Rebuild hard state from chapters.")
    parser.add_argument("--chapters-dir", type=str, default="../chapters", help="Chapters root directory")
    parser.add_argument("--reset", action="store_true", help="Reset existing state files before rebuild")
    parser.add_argument("--force", action="store_true", help="Commit updates even if errors exist")
    args = parser.parse_args()

    project_path = PROJECT_PATH
    chapters_dir = (Path(__file__).resolve().parent / args.chapters_dir).resolve()

    manager = StoryStateManager(project_path=project_path)

    if args.reset:
        if manager.snapshot_path.exists():
            manager.snapshot_path.unlink()
        if manager.events_path.exists():
            manager.events_path.unlink()
        manager.load()

    report = []
    chapters = collect_chapters(chapters_dir)
    for chapter_num, path in chapters:
        text = path.read_text(encoding="utf-8")
        snapshot = manager.get_snapshot(chapter_num)
        issues = manager.validate_chapter(text, snapshot)
        updates = manager.extract_state_updates(text, chapter_num)

        entry = {
            "chapter": chapter_num,
            "file": str(path),
            "issues": issues,
            "updates": updates,
        }
        report.append(entry)

        if issues and not args.force:
            continue

        manager.commit(chapter_num, updates, issues, persist=True)

    report_path = project_path / "state" / "consistency_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Rebuild completed. Report: {report_path}")


if __name__ == "__main__":
    main()
