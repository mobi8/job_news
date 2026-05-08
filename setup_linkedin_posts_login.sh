#!/usr/bin/env bash
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${WORKDIR}"

export LINKEDIN_POSTS_PROFILE_DIR="${LINKEDIN_POSTS_PROFILE_DIR:-${WORKDIR}/outputs/linkedin-post-profile}"
mkdir -p "${LINKEDIN_POSTS_PROFILE_DIR}"

node linkedin_posts_login_setup.js
