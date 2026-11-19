import threading
from datetime import datetime, timezone
from urllib.error import URLError

from scripts import generate_readme as generator


def project(name, url):
    return {
        "name": name,
        "url": url,
        "category": "Libraries",
        "description": name,
    }


def metadata(archived=False):
    return {
        "stargazers_count": 1234,
        "pushed_at": datetime.now(timezone.utc).isoformat(),
        "archived": archived,
    }


def test_requests_overlap_with_at_most_eight_workers(monkeypatch):
    projects = [
        project(str(i), f"https://github.com/owner/repo{i}/tree/main/src")
        for i in range(16)
    ]
    barrier = threading.Barrier(8, timeout=10)
    lock = threading.Lock()
    active = 0
    peak = 0
    calls = []

    def fetch(path, token, params=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append((path, token, params))
        try:
            # All eight workers must reach each batch, in both request phases.
            barrier.wait()
            if params:
                return [{"commit": {"committer": {"date": metadata()["pushed_at"]}}}]
            return metadata()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(generator, "github_get", fetch)
    results = generator.collect_metadata(projects, "test-token")

    assert peak == 8
    assert len(calls) == 32
    assert all(token == "test-token" for _, token, _ in calls)
    assert list(results) == [id(p) for p in projects]
    assert all(r["stars"] == "1.2k 🔥" for r in results.values())
    assert all(r["status"] == "🟢" for r in results.values())
    table = generator.render_table(projects, results)
    assert table.index("[0]") < table.index("[15]")


def test_shared_targets_are_deduplicated_and_non_github_is_skipped(monkeypatch):
    projects = [
        project("Root", "https://github.com/owner/repo"),
        project("Path", "https://github.com/owner/repo/tree/main/src"),
        project("Same path", "https://github.com/owner/repo/tree/main/src"),
        project("Website", "https://example.com"),
    ]
    calls = []

    def fetch(path, token, params=None):
        calls.append((path, token, params))
        return [] if params else metadata()

    monkeypatch.setattr(generator, "github_get", fetch)
    results = generator.collect_metadata(projects, None)

    assert calls == [
        ("/repos/owner/repo", None, None),
        ("/repos/owner/repo/commits", None, {"path": "src", "per_page": "1"}),
    ]
    assert results[id(projects[0])]["status"] == "🟢"
    assert results[id(projects[1])]["status"] == "❓"
    assert results[id(projects[1])] == results[id(projects[2])]
    assert results[id(projects[3])]["stars"] == "N/A"
    assert results[id(projects[3])]["status"] == "N/A"


def test_failures_preserve_fallbacks_and_sorted_warnings(monkeypatch, capsys):
    projects = [
        project("Missing", "https://github.com/z/missing/tree/main/src"),
        project("Path error", "https://github.com/a/repo/tree/main/broken"),
        project("Old path", "https://github.com/a/repo/tree/main/old"),
        project("Archived", "https://github.com/a/archive"),
    ]
    calls = []

    def fetch(path, token, params=None):
        calls.append((path, params))
        if path == "/repos/z/missing":
            raise URLError("unavailable")
        if params and params["path"] == "broken":
            raise ValueError("invalid JSON")
        if params:
            return [{"commit": {"author": {"date": "2000-01-01T00:00:00Z"}}}]
        return metadata(archived=path.endswith("/archive"))

    monkeypatch.setattr(generator, "github_get", fetch)
    results = generator.collect_metadata(projects, None)

    assert ("/repos/z/missing/commits", {"path": "src", "per_page": "1"}) not in calls
    assert results[id(projects[0])]["stars"] == "—"
    assert results[id(projects[0])]["status"] == "❓"
    assert results[id(projects[1])]["stars"] == "1.2k 🔥"
    assert results[id(projects[1])]["status"] == "❓"
    assert results[id(projects[2])]["status"] == "⚪"
    assert results[id(projects[3])]["status"] == "📦"
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert "a/repo/broken: invalid JSON" in lines[0]
    assert "z/missing:" in lines[1]
