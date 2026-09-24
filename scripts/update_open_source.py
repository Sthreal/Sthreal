#!/usr/bin/env python3
"""Update the open-source contribution tables in the profile README."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USERNAME = os.environ.get("PROFILE_USERNAME", "Sthreal")
TOKEN = os.environ.get("GITHUB_TOKEN")
README_PATH = Path(os.environ.get("README_PATH", "README.md"))
START_MARKER = "<!-- OPEN_SOURCE_CONTRIBUTIONS:START -->"
END_MARKER = "<!-- OPEN_SOURCE_CONTRIBUTIONS:END -->"

DESCRIPTIONS = {
    "https://github.com/helsome/folio/pull/85": (
        "Enforced wall-clock run budgets while an agent event stream is silent"
    ),
    "https://github.com/helsome/folio/pull/183": (
        "Prevented uncooperative capabilities from bypassing execution timeouts"
    ),
    "https://github.com/Tencent/BrowserSkill/pull/329": (
        "Scoped `doctor` skill status to the bundled CLI version"
    ),
    "https://github.com/assistant-ui/assistant-ui/pull/8071": (
        "Fixed duplicate `assistant-cloud` instances by reusing the host `ai` peer"
    ),
    "https://github.com/helsome/folio/pull/186": (
        "Removed a provider timeout abort-listener leak"
    ),
    "https://github.com/mastra-ai/mastra/pull/24477": (
        "Coordinated Docker termination settlement metadata"
    ),
    "https://github.com/QwenLM/qwen-code/pull/12233": (
        "Preserved MCP OAuth registration URL during discovery"
    ),
    "https://github.com/modelcontextprotocol/typescript-sdk/pull/2846": (
        "Updated `eventsource-parser` for large SSE responses"
    ),
    "https://github.com/TencentCloud/octop-harness/pull/10": (
        "Avoided cross-context session-header resets in streamed agents"
    ),
}


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int
    title: str
    url: str
    state: str
    merged_at: str | None
    updated_at: str

    @property
    def description(self) -> str:
        return DESCRIPTIONS.get(self.url, self.title)


def github_request(url: str) -> dict[str, object]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Sthreal-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc


def fetch_pull_requests() -> list[PullRequest]:
    query = f"is:pr author:{USERNAME} is:public -user:{USERNAME}"
    pull_requests: list[PullRequest] = []

    for page in range(1, 11):
        params = urlencode(
            {
                "q": query,
                "sort": "updated",
                "order": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        payload = github_request(f"https://api.github.com/search/issues?{params}")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("GitHub search response did not contain an items list")

        for item in items:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state", ""))
            pull_request = item.get("pull_request")
            if not isinstance(pull_request, dict):
                continue

            merged_at = pull_request.get("merged_at")
            merged_at = str(merged_at) if merged_at else None
            if state != "open" and merged_at is None:
                continue

            repository_url = str(item.get("repository_url", ""))
            repository = repository_url.split("/repos/", 1)[-1]
            if not repository:
                continue

            pull_requests.append(
                PullRequest(
                    repository=repository,
                    number=int(item["number"]),
                    title=str(item.get("title", "")).strip(),
                    url=str(item.get("html_url", "")).strip(),
                    state=state,
                    merged_at=merged_at,
                    updated_at=str(item.get("updated_at", "")),
                )
            )

        if len(items) < 100:
            break

    return pull_requests


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def pull_request_table(pull_requests: list[PullRequest]) -> list[str]:
    lines = [
        "| Project | Contribution | PR |",
        "|---|---|---|",
    ]
    for pull_request in pull_requests:
        project = f"[{pull_request.repository}](https://github.com/{pull_request.repository})"
        contribution = escape_cell(pull_request.description)
        link = f"[#{pull_request.number}]({pull_request.url})"
        lines.append(f"| {project} | {contribution} | {link} |")
    return lines


def render_section(pull_requests: list[PullRequest]) -> str:
    merged = sorted(
        (pr for pr in pull_requests if pr.merged_at),
        key=lambda pr: pr.merged_at or pr.updated_at,
        reverse=True,
    )
    in_review = sorted(
        (pr for pr in pull_requests if pr.state == "open"),
        key=lambda pr: pr.updated_at,
        reverse=True,
    )

    lines = [
        START_MARKER,
        "## Open Source Contributions",
        "",
        f"> Automatically updated daily · {len(merged)} merged · {len(in_review)} in review",
        "",
        "### Merged Pull Requests",
        "",
    ]
    lines.extend(
        pull_request_table(merged)
        if merged
        else ["_No merged external pull requests yet._"]
    )
    lines.extend(
        [
            "",
            "### Pull Requests In Review",
            "",
        ]
    )
    lines.extend(
        pull_request_table(in_review)
        if in_review
        else ["_No open external pull requests._"]
    )
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_readme(readme: str, section: str) -> str:
    if START_MARKER not in readme or END_MARKER not in readme:
        raise RuntimeError(
            f"README must contain both {START_MARKER} and {END_MARKER}"
        )

    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    return pattern.sub(section, readme, count=1)


def main() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    pull_requests = fetch_pull_requests()
    updated = update_readme(readme, render_section(pull_requests))

    if updated != readme:
        README_PATH.write_text(updated, encoding="utf-8", newline="\n")
        print("README updated")
    else:
        print("README already up to date")


if __name__ == "__main__":
    main()
