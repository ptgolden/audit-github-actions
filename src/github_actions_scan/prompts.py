from pathlib import Path

import typer

from .models import (
    CHOICE_EXACT,
    CHOICE_MAJOR,
    CHOICE_SHA,
    CHOICE_SKIP,
    ActionUpdate,
    Decision,
    LatestRelease,
)


STATUS_OUTDATED = "outdated"

_CHOICE_FROM_KEY = {
    "m": CHOICE_MAJOR,
    "e": CHOICE_EXACT,
    "s": CHOICE_SHA,
    "n": CHOICE_SKIP,
}


_HELP_TEXT = """
  (m) pin to major tag:  rewrite to use the moving major-version tag (e.g. v6).
                         Auto-tracks future v6.x.y releases.
  (e) pin to exact tag:  rewrite to use the latest exact release tag
                         (e.g. v6.0.2). Immutable for that release.
  (s) pin to SHA:        rewrite to use the immutable commit SHA. Most secure
                         (no supply-chain surprise from a moving tag).
  (n) leave as is:       keep the current pin unchanged.
  (A) apply previous:    re-use the choice you made for this WORKFLOW@TAG combo
                         on every remaining occurrence of it.
  (q) quit:              stop prompting; keep choices made so far.
  (?) help:              this message.
"""


def _find_line(file_path: Path, uses_target: str) -> int | None:
    """Return the first 1-indexed line in file_path where uses_target appears with `uses:`."""
    if not file_path.is_file():
        return None
    for i, line in enumerate(file_path.read_text().splitlines(), start=1):
        if "uses:" in line and uses_target in line:
            return i
    return None


def _context_lines(file_path: Path, target_line: int, padding: int = 5) -> list[str]:
    """Return formatted ±padding lines around target_line (1-indexed) with line numbers."""
    lines = file_path.read_text().splitlines()
    start = max(1, target_line - padding)
    end = min(len(lines), target_line + padding)
    out = []
    for i in range(start, end + 1):
        marker = ">" if i == target_line else " "
        out.append(f"  {marker} {i:>4}│ {lines[i - 1]}")
    return out


def _short_sha(sha: str) -> str:
    return sha[:8] if sha else ""


def _format_prior(prior_choice: str, latest: LatestRelease | None) -> str:
    """Render the 'apply previous' summary text, e.g. 'exact: v6.0.2'."""
    if prior_choice == CHOICE_SKIP or latest is None:
        return prior_choice
    if prior_choice == CHOICE_MAJOR and latest.latest_major_tag:
        return f"{prior_choice}: {latest.latest_major_tag}"
    if prior_choice == CHOICE_EXACT and latest.tag_name:
        return f"{prior_choice}: {latest.tag_name}"
    if prior_choice == CHOICE_SHA and latest.latest_sha:
        return f"{prior_choice}: {_short_sha(latest.latest_sha)}"
    return prior_choice


def _print_prompt(
    update: ActionUpdate,
    clone_path: Path,
    position: int,
    total: int,
    prior_choice: str | None,
    pending_matches: int,
) -> tuple[list[str], bool]:
    """Print the per-action prompt block.

    Returns (valid_keys, major_available) so the input loop can validate.
    """
    workflow_file = clone_path / update.workflow_path
    line_no = _find_line(workflow_file, update.uses_target)
    latest = update.latest_release

    print()
    print(f"[{position}/{total}] {update.uses_target}")
    file_label = (
        f"{workflow_file}:{line_no}" if line_no else str(workflow_file)
    )
    print(f"      File:   {file_label}")
    print(f"      Action: https://github.com/{update.uses_repo}")
    print()

    if line_no:
        for line in _context_lines(workflow_file, line_no):
            print(line)
        print()

    current_sha_short = _short_sha(update.current_sha) or "(unknown)"
    current_date = update.current_published_at[:10] or "(unknown)"
    latest_sha_short = (
        _short_sha(latest.latest_sha) if latest and latest.latest_sha else "(unknown)"
    )
    latest_date = (
        latest.published_at[:10] if latest and latest.published_at else "(unknown)"
    )
    latest_tag = latest.tag_name if latest else "(no release)"
    major_tag = latest.latest_major_tag if latest else None

    print(f"  Current: {update.current_ref:<15}  {current_sha_short}  {current_date}")
    print(f"  Latest:  {latest_tag:<15}  {latest_sha_short}  {latest_date}")
    if major_tag:
        print(f"  Major:   {major_tag}")
    print()

    print("  Options:")
    if major_tag:
        print(f"    (m) pin to {major_tag}")
    else:
        print(
            f"    (m) pin to major tag — not available for {update.uses_repo}"
        )
    print(f"    (e) pin to {latest_tag}")
    print(f"    (s) pin to {latest_sha_short}...")
    print("    (n) leave as is")
    if prior_choice is not None and pending_matches > 0:
        prior_label = _format_prior(prior_choice, latest)
        plural = "" if pending_matches == 1 else "s"
        print(
            f"    (A) apply previous choice [{prior_label}] to "
            f"{pending_matches} more occurrence{plural}"
        )
    print("    (q) quit (keep changes made so far)")
    print("    (?) help")
    print()

    valid = ["m", "e", "s", "n", "q", "?"]
    if prior_choice is not None and pending_matches > 0:
        valid.append("A")
    return valid, bool(major_tag)


def _ask_one(
    update: ActionUpdate,
    clone_path: Path,
    position: int,
    total: int,
    prior_choice: str | None,
    pending_matches: int,
) -> str:
    """Show the prompt and return a valid choice key (one of m/e/s/n/A/q)."""
    valid, major_available = _print_prompt(
        update, clone_path, position, total, prior_choice, pending_matches
    )
    while True:
        try:
            raw = input(f"  Choose [{'/'.join(valid)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"

        if raw == "?":
            print(_HELP_TEXT)
            continue
        if raw not in valid:
            print(f"  Not a valid choice. Pick one of [{'/'.join(valid)}].")
            continue
        if raw == "m" and not major_available:
            print(
                f"  (m) is not available: {update.uses_repo} does not "
                "publish a moving major-version tag."
            )
            continue
        return raw


def prompt_for_decisions(
    clone_path: Path,
    updates: list[ActionUpdate],
) -> list[Decision]:
    """Run the interactive prompt loop over outdated updates.

    Skips up-to-date and other non-outdated rows entirely. Returns the
    accumulated decisions, including any partial set if the user quits early.
    """
    outdated = [u for u in updates if u.status == STATUS_OUTDATED]
    if not outdated:
        print("Nothing to update — every external action is already up to date.")
        return []

    plural = "" if len(outdated) == 1 else "s"
    print(
        f"Found {len(outdated)} outdated action use{plural} across "
        f"{len({u.workflow_path for u in outdated})} workflow file"
        f"{'' if len({u.workflow_path for u in outdated}) == 1 else 's'}."
    )
    if not typer.confirm("Proceed with interactive review?", default=True):
        return []

    decisions: list[Decision] = []
    prior_by_target: dict[str, str] = {}
    pending: list[ActionUpdate] = list(outdated)
    completed = 0
    total = len(outdated)

    while pending:
        update = pending.pop(0)
        completed += 1
        prior = prior_by_target.get(update.uses_target)
        pending_matches = sum(
            1 for u in pending if u.uses_target == update.uses_target
        )

        key = _ask_one(
            update,
            clone_path,
            position=completed,
            total=total,
            prior_choice=prior,
            pending_matches=pending_matches,
        )

        if key == "q":
            print("  quitting; keeping decisions made so far.")
            break

        if key == "A":
            assert prior is not None  # menu only offered A when prior was set
            decisions.append(
                Decision(
                    workflow_path=update.workflow_path,
                    uses_target=update.uses_target,
                    choice=prior,
                )
            )
            applied_to = 1
            remaining: list[ActionUpdate] = []
            for u in pending:
                if u.uses_target == update.uses_target:
                    decisions.append(
                        Decision(
                            workflow_path=u.workflow_path,
                            uses_target=u.uses_target,
                            choice=prior,
                        )
                    )
                    applied_to += 1
                else:
                    remaining.append(u)
            pending = remaining
            plural = "" if applied_to == 1 else "s"
            print(
                f"  applied [{_format_prior(prior, update.latest_release)}] to "
                f"{applied_to} occurrence{plural}."
            )
            continue

        choice_name = _CHOICE_FROM_KEY[key]
        decisions.append(
            Decision(
                workflow_path=update.workflow_path,
                uses_target=update.uses_target,
                choice=choice_name,
            )
        )
        prior_by_target[update.uses_target] = choice_name

    return decisions
