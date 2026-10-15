#!/usr/bin/env python3
"""Sync Theblackcat98's GitHub stars into data/stars.json and README.md.

Runs in GitHub Actions (daily) and locally. Stdlib only.

Environment:
    GITHUB_TOKEN  optional — raises the API rate limit (recommended in CI).

Exit code 0 always; prints a short summary.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

USER = "theblackcat98"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
STARS_JSON = os.path.join(DATA_DIR, "stars.json")
CATEGORIES_JSON = os.path.join(DATA_DIR, "categories.json")
README = os.path.join(ROOT, "README.md")

START_MARKER = "<!-- STARS:START -->"
END_MARKER = "<!-- STARS:END -->"


def api_get(url):
    headers = {
        "Accept": "application/vnd.github.star+json",
        "User-Agent": "github-stars-sync",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.load(resp), resp.headers.get("X-RateLimit-Remaining")


def fetch_stars():
    stars = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{USER}/starred?per_page=100&page={page}"
        items, remaining = api_get(url)
        for item in items:
            repo = item["repo"]
            stars.append(
                {
                    "full_name": repo["full_name"],
                    "html_url": repo["html_url"],
                    "description": repo.get("description") or "",
                    "language": repo.get("language") or "",
                    "stargazers_count": repo.get("stargazers_count", 0),
                    "topics": repo.get("topics", []),
                    "starred_at": item.get("starred_at", ""),
                }
            )
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.5)
    return stars


def esc(text):
    """Make a string safe for a Markdown table cell."""
    return (
        (text or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("|", "\\|")
        .strip()
    )


def anchor(name):
    slug = re.sub(r"[^\w\- ]", "", name.lower()).replace(" ", "-")
    return slug


def main():
    stars = fetch_stars()

    categories = {}
    if os.path.exists(CATEGORIES_JSON):
        with open(CATEGORIES_JSON) as f:
            categories = json.load(f)

    # Preserve the category order from the mapping file; Uncategorized last.
    order = []
    seen = set()
    for cats in categories.values():
        for c in cats:
            if c not in seen:
                seen.add(c)
                order.append(c)
    for s in stars:
        for c in categories.get(s["full_name"], ["Uncategorized"]):
            if c not in seen:
                seen.add(c)
                order.append(c)
    order = [c for c in order if c != "Uncategorized"] + (
        ["Uncategorized"] if "Uncategorized" in seen else []
    )

    by_cat = {c: [] for c in order}
    for s in stars:
        s["categories"] = categories.get(s["full_name"], ["Uncategorized"])
        for c in s["categories"]:
            by_cat.setdefault(c, []).append(s)
    for repos in by_cat.values():
        repos.sort(key=lambda r: r["full_name"].lower())

    with open(STARS_JSON, "w") as f:
        json.dump(stars, f, indent=1, sort_keys=True)
        f.write("\n")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"**{len(stars)} repositories** · last synced {now}",
        "",
        "## Categories",
        "",
    ]
    for c in order:
        lines.append(f"- [{c} ({len(by_cat[c])})](#{anchor(c)})")
    lines.append("")
    for c in order:
        lines.extend(
            [
                f"## {c}",
                "",
                "| Repo | ★ | Language | Description |",
                "| ---- | -: | -------- | ----------- |",
            ]
        )
        for r in by_cat[c]:
            name = f"[{r['full_name']}]({r['html_url']})"
            lines.append(
                f"| {name} | {r['stargazers_count']} | {esc(r['language'])} "
                f"| {esc(r['description'])} |"
            )
        lines.append("")

    body = "\n".join(lines)

    with open(README) as f:
        readme = f.read()
    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    new_readme = readme[:start] + "\n" + body + readme[end:]
    with open(README, "w") as f:
        f.write(new_readme)

    print(f"synced {len(stars)} stars across {len(order)} categories")


if __name__ == "__main__":
    sys.exit(main())
