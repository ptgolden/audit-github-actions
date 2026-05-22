import csv
import sys
from typing import Iterable

from loguru import logger
from tqdm import tqdm

from .github import GitHubClient
from .models import (
    UPDATE_REPORT_COLUMNS,
    ActionUpdate,
    LatestRelease,
    Repo,
)
from .releases import fetch_latest_release
from .scan import dedupe_scan_records, scan_repo_workflows


STATUS_UP_TO_DATE = "up_to_date"
STATUS_OUTDATED = "outdated"
STATUS_NO_RELEASE = "no_release"
STATUS_REF_UNKNOWN = "ref_unknown"


def compute_status(current_ref: str, latest: LatestRelease | None) -> str:
    """Classify an action use as up-to-date, outdated, missing-release, or unknown."""
    if not current_ref:
        return STATUS_REF_UNKNOWN
    if latest is None:
        return STATUS_NO_RELEASE
    if current_ref == latest.tag_name:
        return STATUS_UP_TO_DATE
    return STATUS_OUTDATED


def find_action_updates(
    client: GitHubClient,
    repo: Repo,
    progress: bool,
) -> list[ActionUpdate]:
    """Scan a repo's workflows and look up the latest release for each unique action."""
    records = dedupe_scan_records(scan_repo_workflows(client, repo))

    unique_repos = sorted({record.uses_repo for record in records if record.uses_repo})
    if progress:
        logger.info(
            "found {} workflow uses across {} unique action repos",
            len(records),
            len(unique_repos),
        )

    progress_bar: tqdm[str] | None = None
    repo_iterable: Iterable[str]
    if progress:
        progress_bar = tqdm(
            unique_repos,
            desc="releases",
            unit="repo",
            file=sys.stderr,
            dynamic_ncols=True,
        )
        progress_bar.set_postfix_str(f"gh api calls={client.api_call_count}")
        repo_iterable = progress_bar
    else:
        repo_iterable = unique_repos

    latest_by_repo: dict[str, LatestRelease | None] = {}
    for uses_repo in repo_iterable:
        logger.debug("fetching latest release for {}", uses_repo)
        latest_by_repo[uses_repo] = fetch_latest_release(client, uses_repo)
        if progress_bar:
            progress_bar.set_postfix_str(f"gh api calls={client.api_call_count}")

    return [
        ActionUpdate(
            workflow_path=record.workflow_path,
            uses_target=record.uses_target,
            uses_repo=record.uses_repo,
            uses_path=record.uses_path,
            current_ref=record.ref,
            latest_release=latest_by_repo.get(record.uses_repo),
            status=compute_status(record.ref, latest_by_repo.get(record.uses_repo)),
        )
        for record in records
    ]


def write_update_report(updates: Iterable[ActionUpdate], include_header: bool) -> None:
    """Write one TSV row per workflow action use, including latest-release info."""
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=UPDATE_REPORT_COLUMNS,
        delimiter="\t",
        lineterminator="\n",
        extrasaction="ignore",
    )
    if include_header:
        writer.writeheader()

    for update in updates:
        latest = update.latest_release
        writer.writerow(
            {
                "workflow_path": update.workflow_path,
                "uses_target": update.uses_target,
                "uses_repo": update.uses_repo,
                "uses_path": update.uses_path,
                "current_ref": update.current_ref,
                "latest_tag": latest.tag_name if latest else "",
                "latest_published_at": latest.published_at if latest else "",
                "latest_url": latest.html_url if latest else "",
                "status": update.status,
            }
        )
