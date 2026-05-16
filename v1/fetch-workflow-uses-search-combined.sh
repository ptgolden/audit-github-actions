#!/usr/bin/env bash
set -euo pipefail

# Catalog GitHub Actions workflow files containing "uses" in one organization.
#
# Why three searches?
# GitHub code search pagination can return slightly different result sets for a
# broad query versus narrower extension-qualified queries. The three searches
# below are cheap enough to run together, and merging them improves recall:
#
#   1. Any matching file under .github/workflows
#   2. Matching .yml files under .github/workflows
#   3. Matching .yaml files under .github/workflows
#
# The Accept header asks GitHub to include text_matches. These are search
# snippets around the matched term, not guaranteed complete lines and not
# line-numbered, but they usually include the relevant "uses:" line.
#
# The final JSON preserves all raw result objects, including text_matches and
# repository metadata included by the Search API. Items are de-duplicated by
# repository full name, path, and blob SHA.
#
# Configure the organization with:
#
#   ORGANIZATION_NAME=monarch-initiative ./fetch-workflow-uses-search-combined.sh
#
# Output:
#
#   workflow-uses-search-combined-${ORGANIZATION_NAME}.json

ORGANIZATION_NAME="${ORGANIZATION_NAME:-monarch-initiative}"
out="workflow-uses-search-combined-${ORGANIZATION_NAME}.json"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

run_query() {
  local slug="$1"
  local query="$2"
  local pages="$tmpdir/${slug}.pages.json"
  local summary="$tmpdir/${slug}.json"

  gh api --paginate --method GET search/code \
    -H 'Accept: application/vnd.github.text-match+json' \
    -f q="$query" \
    -f per_page=100 > "$pages"

  jq -s --arg slug "$slug" --arg query "$query" '
    {
      slug: $slug,
      query: $query,
      total_count: (.[0].total_count // 0),
      incomplete_results: (map(.incomplete_results) | any),
      item_count: (map(.items | length) | add),
      pages: map({
        total_count,
        incomplete_results,
        item_count: (.items | length)
      }),
      items: (map(.items) | add)
    }
  ' "$pages" > "$summary"
}

run_query \
  "workflow-any-extension" \
  "uses org:${ORGANIZATION_NAME} in:file path:.github/workflows"

run_query \
  "workflow-yml" \
  "uses org:${ORGANIZATION_NAME} in:file path:.github/workflows extension:yml"

run_query \
  "workflow-yaml" \
  "uses org:${ORGANIZATION_NAME} in:file path:.github/workflows extension:yaml"

jq -s --arg organization "$ORGANIZATION_NAME" '
  def item_key:
    .repository.full_name + "\u0000" + .path + "\u0000" + .sha;

  {
    organization: $organization,
    description: "GitHub code search results for workflow files containing uses. Includes broad and extension-qualified searches, with text_matches when GitHub returns them.",
    dedupe_key: "repository.full_name + path + sha",
    queries: map({
      slug,
      query,
      total_count,
      incomplete_results,
      item_count,
      pages
    }),
    item_count_before_dedupe: (map(.items | length) | add),
    items: (
      map(.items) | add
      | unique_by(item_key)
    )
  }
  | .item_count = (.items | length)
  | .query_count = (.queries | length)
  | .incomplete_results = ([.queries[].incomplete_results] | any)
' \
  "$tmpdir/workflow-any-extension.json" \
  "$tmpdir/workflow-yml.json" \
  "$tmpdir/workflow-yaml.json" > "$out"

printf 'Wrote %s\n' "$out"
