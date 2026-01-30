"""Minimal regression test for warehouse hard-state guard."""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import yaml

PROJECT_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_PATH))

from story_state_manager import StoryStateManager


def has_error(issues):
    return any(issue.get("severity") == "error" for issue in issues)


def write_yaml(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_warehouse_guard():
    with TemporaryDirectory() as tmp:
        project_path = Path(tmp)
        write_yaml(
            project_path / "worldbook" / "system_state.yaml",
            {
                "system": {
                    "warehouse": {
                        "accessible": False,
                        "unlocked_by": None,
                        "last_update_chapter": 0,
                        "evidence": "初始：系统仓库不可打开",
                        "strict": True,
                    }
                }
            },
        )
        write_yaml(
            project_path / "worldbook" / "invariants.yaml",
            {
                "invariants": [
                    {
                        "id": "system.warehouse.strict_access",
                        "description": "仓库不可用时不得成功访问",
                        "scope_keywords": ["仓库", "系统仓库", "库存"],
                        "severity": "error",
                    }
                ]
            },
        )

        manager = StoryStateManager(project_path=project_path)

        snapshot1 = manager.get_snapshot(1)
        assert snapshot1["state"]["system"]["warehouse"]["accessible"] is False

        chapter1 = "他尝试打开系统仓库，但提示权限不足，无法打开。"
        issues1 = manager.validate_chapter(chapter1, snapshot1)
        assert not has_error(issues1)

        updates1 = manager.extract_state_updates(chapter1, 1)
        manager.commit(1, updates1, issues1, persist=False)

        snapshot2 = manager.get_snapshot(2)
        chapter2 = "艾伦打开仓库，成功取出物品。"
        issues2 = manager.validate_chapter(chapter2, snapshot2)
        assert has_error(issues2)


if __name__ == "__main__":
    test_warehouse_guard()
    print("OK")
