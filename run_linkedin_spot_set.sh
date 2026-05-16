#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

LOCATION="${1:-}"
KEYWORDS="${2:-crypto,web3,payments,igaming,product}"
LIMIT="${3:-8}"

if [[ -z "${LOCATION}" ]]; then
  echo "Usage: ./run_linkedin_spot_set.sh <location> [keyword1,keyword2] [limit]" >&2
  echo "Example: ./run_linkedin_spot_set.sh \"Amsterdam\" \"crypto,web3,payments\" 8" >&2
  exit 2
fi

cd "${WORKDIR}"

echo "== LinkedIn spot set: ${LOCATION} | ${KEYWORDS} | limit=${LIMIT}"
echo "== 1/2 LinkedIn posts"
"${WORKDIR}/run_linkedin_posts.sh" spot "${LOCATION}" "${KEYWORDS}" "${LIMIT}"

echo "== 2/2 LinkedIn jobs board"
"${WORKDIR}/run_linkedin_jobs_spot.sh" "${LOCATION}" "${KEYWORDS}" "${LIMIT}"

echo "== Done: posts + jobs board only; news was not scraped."
