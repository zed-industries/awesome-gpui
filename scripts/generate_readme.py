#!/usr/bin/env -S uv run --script
"""Generate README.md from projects.json and current GitHub metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_PATH = ROOT / "projects.json"
TEMPLATE_PATH = ROOT / "README.template.md"
README_PATH = ROOT / "README.md"
PLACEHOLDER = "<!-- PROJECTS -->"
API_ROOT = "https://api.github.com"



def github_get(path: str, token: str | None, params: dict[str, str] | None = None) -> Any:
    url = f"{API_ROOT}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "awesome-gpui-readme-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def activity_details(date: datetime | None, archived: bool = False) -> tuple[str, str]:
    last_commit = date.date().isoformat() if date is not None else "N/A"
    if archived:
        return "📦", last_commit
    if date is None:
        return "❓", last_commit

    days = max(0, (datetime.now(timezone.utc) - date).days)
    if days <= 90:
        return "🟢", last_commit
    if days <= 365:
        return "🟡", last_commit
    return "⚪", last_commit


def compact_stars(value: int | None) -> str:
    if value is None:
        return "—"
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        number, suffix = value / 1_000, "k"
    else:
        number, suffix = value / 1_000_000, "m"
    precision = 1 if number < 100 else 0
    return f"{number:.{precision}f}".rstrip("0").rstrip(".") + suffix


def star_display(value: int | None) -> str:
    stars = compact_stars(value)
    return f"{stars} 🔥" if value is not None and value >= 1_000 else stars


def escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def repository_link(project: dict[str, Any], metadata: dict[str, Any] | None) -> str:
    if "url" in project:
        return project["url"]
    repository = project["repository"]
    base = str(metadata.get("html_url") or f"https://github.com/{repository}") if metadata else f"https://github.com/{repository}"
    if project.get("path"):
        branch = metadata.get("default_branch", "main") if metadata else "main"
        path = quote(project["path"], safe="/")
        return f"{base}/tree/{quote(branch, safe='')}/{path}"
    return base


def render_table(projects: list[dict[str, Any]], results: dict[int, dict[str, Any]]) -> str:
    lines = [
        "| Image | Project | Description | Stars | Status | Last Commit |",
        "| --- | --- | --- | ---: | :---: | --- |",
    ]
    for project in projects:
        result = results[id(project)]
        link = repository_link(project, result.get("metadata"))
        name = escape_cell(project["name"])
        description = escape_cell(project["description"])
        image = project.get("image")
        image_cell = f'<img src="{escape(image, quote=True)}" alt="" height="64">' if image else ""
        lines.append(
            f"| {image_cell} | [{name}]({link}) | {description} | {result['stars']} | "
            f"{result['status']} | {result['last_commit']} |"
        )
    return "\n".join(lines)


def group_projects(
    projects: list[dict[str, Any]],
) -> dict[str, dict[str | None, list[dict[str, Any]]]]:
    catalog: dict[str, dict[str | None, list[dict[str, Any]]]] = {}
    for project in projects:
        category = project["category"]
        subcategory = project.get("subcategory")
        catalog.setdefault(category, {}).setdefault(subcategory, []).append(project)
    return catalog


def render_catalog(
    catalog: dict[str, dict[str | None, list[dict[str, Any]]]],
    results: dict[int, dict[str, Any]],
) -> str:
    sections = [
        "**Key:** 🔥 1,000+ stars · 🟢 active (≤90 days) · "
        "🟡 quiet (91–365 days) · ⚪ dormant (>365 days) · "
        "📦 archived · ❓ unavailable"
    ]
    for category, subcategories in catalog.items():
        sections.append(f"## {category}")
        if None in subcategories:
            sections.append(render_table(subcategories[None], results))
            continue

        for subcategory, entries in subcategories.items():
            if subcategory is not None:
                sections.extend([f"### {subcategory}", render_table(entries, results)])

    return "\n\n".join(sections)


def collect_metadata(projects: list[dict[str, Any]], token: str | None) -> dict[int, dict[str, Any]]:
    repositories: dict[str, dict[str, Any] | None] = {}
    errors: set[str] = set()

    for project in projects:
        repository = project.get("repository")
        if not repository or repository in repositories:
            continue
        try:
            repositories[repository] = github_get(f"/repos/{repository}", token)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            repositories[repository] = None
            errors.add(f"{repository}: {error}")

    results: dict[int, dict[str, Any]] = {}
    for project in projects:
        repository = project.get("repository")
        if repository is None:
            results[id(project)] = {
                "metadata": None,
                "stars": "N/A",
                "status": "N/A",
                "last_commit": "N/A",
            }
            continue

        metadata = repositories.get(repository)
        if metadata is None:
            results[id(project)] = {
                "metadata": None,
                "stars": "—",
                "status": "❓",
                "last_commit": "N/A",
            }
            continue

        date = parse_date(metadata.get("pushed_at"))
        if project.get("path"):
            try:
                commits = github_get(
                    f"/repos/{repository}/commits",
                    token,
                    {"path": project["path"], "per_page": "1"},
                )
                if commits:
                    commit = commits[0].get("commit", {})
                    date = parse_date(commit.get("committer", {}).get("date")) or parse_date(
                        commit.get("author", {}).get("date")
                    )
                else:
                    date = None
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                date = None
                errors.add(f"{repository}/{project['path']}: {error}")

        status, last_commit = activity_details(date, bool(metadata.get("archived")))
        results[id(project)] = {
            "metadata": metadata,
            "stars": star_display(metadata.get("stargazers_count")),
            "status": status,
            "last_commit": last_commit,
        }

    for error in sorted(errors):
        print(f"warning: GitHub metadata unavailable for {error}", file=sys.stderr)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if README.md is not current")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    token = os.environ.get("GITHUB_TOKEN")
    data = json.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    projects = data["projects"]
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise ValueError(f"{TEMPLATE_PATH.name} must contain exactly one {PLACEHOLDER} marker")

    catalog = group_projects(projects)
    results = collect_metadata(projects, token)
    generated = template.replace(PLACEHOLDER, render_catalog(catalog, results)).rstrip() + "\n"

    if args.check:
        current = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""
        if current != generated:
            print("README.md is out of date; run `uv run scripts/generate_readme.py`.", file=sys.stderr)
            return 1
        print("README.md is current.")
        return 0

    README_PATH.write_text(generated, encoding="utf-8")
    print(f"Generated {README_PATH.relative_to(ROOT)} with {len(projects)} projects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
