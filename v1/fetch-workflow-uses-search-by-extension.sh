#!/usr/bin/env bash
set -euo pipefail

ORGANIZATION_NAME="${ORGANIZATION_NAME:-monarch-initiative}"
out="workflow-uses-search-by-extension-${ORGANIZATION_NAME}.json"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

for extension in yml yaml; do
  query="uses org:${ORGANIZATION_NAME} in:file path:.github/workflows extension:${extension}"
  gh api --paginate --method GET search/code \
    -H 'Accept: application/vnd.github.text-match+json' \
    -f q="$query" \
    -f per_page=100 > "$tmpdir/${extension}.pages.json"

  jq -s --arg query "$query" --arg extension "$extension" '
    {
      extension: $extension,
      query: $query,
      total_count: (.[0].total_count // 0),
      incomplete_results: (map(.incomplete_results) | any),
      item_count: (map(.items | length) | add),
      items: (map(.items) | add)
    }
  ' "$tmpdir/${extension}.pages.json" > "$tmpdir/${extension}.json"
done

jq -s --arg organization "$ORGANIZATION_NAME" '
  {
    organization: $organization,
    queries: map({
      extension,
      query,
      total_count,
      incomplete_results,
      item_count
    }),
    item_count_before_dedupe: (map(.items | length) | add),
    items: (
      map(.items) | add
      | unique_by(.repository.full_name + "\u0000" + .path + "\u0000" + .sha)
    )
  }
  | .item_count = (.items | length)
' "$tmpdir/yml.json" "$tmpdir/yaml.json" > "$out"

printf 'Wrote %s\n' "$out"
