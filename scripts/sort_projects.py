#!/usr/bin/env python3
"""Sort projects.json using category order defined by its JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_PATH = ROOT / "projects.json"
SCHEMA_PATH = ROOT / "projects.schema.json"


def enum_order(schema: dict[str, Any], property_name: str) -> dict[str, int]:
    values = schema["$defs"]["project"]["properties"][property_name]["enum"]
    return {value: index for index, value in enumerate(values)}


def sorted_content() -> str:
    data = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    category_order = enum_order(schema, "category")
    subcategory_order = enum_order(schema, "subcategory")

    def sort_key(project: dict[str, Any]) -> tuple[int, int, str, str]:
        category = project["category"]
        subcategory = project.get("subcategory")
        return (
            category_order.get(category, len(category_order)),
            subcategory_order.get(subcategory, len(subcategory_order)),
            project["name"].casefold(),
            project["name"],
        )

    data["projects"] = sorted(data["projects"], key=sort_key)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail instead of rewriting an unsorted file")
    args = parser.parse_args()

    current = PROJECTS_PATH.read_text(encoding="utf-8")
    expected = sorted_content()
    if current == expected:
        print("projects.json is sorted.")
        return 0

    if args.check:
        print(
            "projects.json is not sorted. Run:\n\n"
            "    uv run scripts/sort_projects.py",
            file=sys.stderr,
        )
        return 1

    PROJECTS_PATH.write_text(expected, encoding="utf-8")
    print("Sorted projects.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
