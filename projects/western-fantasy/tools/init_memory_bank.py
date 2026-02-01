"""Initialize memory_bank from worldbook and outline."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_PATH = Path(__file__).resolve().parent.parent
MEMORY_BANK = PROJECT_PATH / "memory_bank"


def read_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    core = MEMORY_BANK / "Core"
    core.mkdir(parents=True, exist_ok=True)

    world_file = core / "world_and_characters.md"
    world_text = world_file.read_text(encoding="utf-8") if world_file.exists() else "# World & Characters\n"

    characters = read_json(PROJECT_PATH / "worldbook" / "characters.json").get("characters", {})
    locations = read_json(PROJECT_PATH / "worldbook" / "locations.json").get("locations", {})
    rules = read_json(PROJECT_PATH / "worldbook" / "rules.json").get("rules", {})

    lines = [world_text.rstrip(), "", "## Characters (from worldbook)"]
    for char in characters.values():
        lines.append(f"- {char.get('name')} ({char.get('type', '')})")

    lines.append("\n## Locations (from worldbook)")
    for loc in locations.values():
        lines.append(f"- {loc.get('name')}")

    lines.append("\n## Rules (from worldbook)")
    for rule in rules.values():
        name = rule.get("name") or "rule"
        lines.append(f"- {name}")

    world_file.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    active = core / "activeContext.md"
    chapter_dir = PROJECT_PATH / "chapters" / "v01"
    current = 0
    if chapter_dir.exists():
        current = len(list(chapter_dir.glob("第*章_*.txt")))

    active_text = active.read_text(encoding="utf-8") if active.exists() else "# Active Context\n"
    if "Current:" in active_text:
        pass
    else:
        active_text += f"\n## Current Chapter\n- Current: Chapter {current}\n"

    active.write_text(active_text.strip() + "\n", encoding="utf-8")

    print("memory_bank initialized")


if __name__ == "__main__":
    main()
