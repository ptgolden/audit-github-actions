# gh-external-audit

Two subcommands for working with GitHub Actions across repositories:

- `org` — scan every repository in an organization for workflow files that pin
  external GitHub Actions, then audit each unique action ref against a set of
  checks. Writes a TSV problem report (one row per workflow use × problem) to
  stdout. Today the only check flags JavaScript actions running on Node older
  than version 24.
- `repo` — scan a single repository's workflows and look up the latest release
  for every external action they use. Writes a TSV update report (one row per
  workflow use, with current ref and latest release info) to stdout.

## Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- [`gh`](https://cli.github.com/) on your `PATH`, authenticated (`gh auth login`)

## Run

```sh
uv run gh-external-audit org ORG > report.tsv
uv run gh-external-audit repo OWNER/REPO > updates.tsv
```

(Or equivalently `uv run python -m gh_external_audit ...`.)

Flags common to both commands:

- `--dry-run` print the planned configuration without calling GitHub
- `--no-progress` suppress stderr progress logs and the tqdm bar
- `--no-header` omit the TSV header row
- `--log-level DEBUG` more verbose progress logging

`org`-only flags:

- `--repo-limit N` (or `REPO_LIMIT=N`) cap how many repos to scan

## Checks

All checks live in `src/gh_external_audit/checks.py`. Each check is a
function that takes a parsed `action.yml` (a `dict`) and yields zero or more
`ProblemRecord(code, detail)` values. The full list is `ACTION_CHECKS`, and
`audit_action` fans out over it.

To add a new check:

1. Write a function `check_my_thing(metadata: dict[str, Any]) -> Iterable[ProblemRecord]`
   that yields one `ProblemRecord` per finding. `code` is the machine-readable
   tag that lands in the `problem` TSV column; `detail` is an optional short
   string for the `detail` column.
2. Append it to `ACTION_CHECKS`.

See `check_node_runtime` for a worked example.
