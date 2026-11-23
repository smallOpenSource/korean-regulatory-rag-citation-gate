#!/usr/bin/env bash
# verify_vite_sri.sh — CI check: every <script src> and <link stylesheet href>
# in the Vite dist/index.html must carry an integrity="sha384-..." attribute.
#
# Usage:
#   scripts/verify_vite_sri.sh [path/to/index.html]
#
# Exits 0 if all tags have SRI. Exits 1 if any are missing or file not found.
# Run after `npm run build` in apps/web/.

set -euo pipefail

DIST_HTML="${1:-apps/web/dist/index.html}"

if [ ! -f "$DIST_HTML" ]; then
  echo "ERROR: '$DIST_HTML' not found — run 'npm run build' in apps/web/ first"
  exit 1
fi

missing=0
checked=0

# Tag-oriented parse: extract each opening <script ...> / <link ...> tag individually
# with `grep -oE` (tag-granular). Minified Vite output frequently puts several tags on
# ONE line; the previous line-oriented `grep integrity=` per line false-PASSED a line
# whenever ANY tag on it carried integrity=, even if a sibling tag on the same line did not.

# Check every <script ... src="..."> tag for an integrity attribute
while IFS= read -r tag; do
  echo "$tag" | grep -qiE 'src=' || continue   # inline scripts (no src) are exempt
  checked=$((checked + 1))
  if ! echo "$tag" | grep -qi 'integrity='; then
    echo "MISSING SRI [script]: $tag"
    missing=$((missing + 1))
  fi
done < <(grep -oiE '<script[^>]*>' "$DIST_HTML")

# Check every <link rel="stylesheet" ... href="..."> tag for an integrity attribute
while IFS= read -r tag; do
  echo "$tag" | grep -qiE 'href=' || continue
  echo "$tag" | grep -qiE 'rel=["\x27]?stylesheet' || continue
  checked=$((checked + 1))
  if ! echo "$tag" | grep -qi 'integrity='; then
    echo "MISSING SRI [stylesheet]: $tag"
    missing=$((missing + 1))
  fi
done < <(grep -oiE '<link[^>]*>' "$DIST_HTML")

if [ "$checked" -eq 0 ]; then
  echo "WARN: No <script src> or <link stylesheet href> tags found in '$DIST_HTML'"
  echo "      Confirm the build output is correct before suppressing this warning."
  exit 1
fi

if [ "$missing" -gt 0 ]; then
  echo ""
  echo "FAIL: $missing of $checked tag(s) in '$DIST_HTML' are missing integrity= attribute"
  echo "      Ensure sriPlugin() is registered in vite.config.ts and rebuild."
  exit 1
fi

echo "OK: All $checked script/stylesheet tag(s) in '$DIST_HTML' carry SRI integrity attributes"
exit 0
