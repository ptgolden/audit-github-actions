import json

from .github import GitHubClient
from .models import LatestRelease


def fetch_latest_release(client: GitHubClient, uses_repo: str) -> LatestRelease | None:
    """Fetch the latest non-prerelease, non-draft release for `owner/repo`.

    Returns None if the repository has no releases (404) or the response is unparseable.
    """
    result = client.api(
        f"/repos/{uses_repo}/releases/latest",
        "-H",
        "Accept: application/vnd.github+json",
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or not data.get("tag_name"):
        return None

    return LatestRelease(
        tag_name=data.get("tag_name") or "",
        name=data.get("name") or "",
        published_at=data.get("published_at") or "",
        html_url=data.get("html_url") or "",
    )
