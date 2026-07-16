#!/bin/sh
# Publish a release without exposing its version to Home Assistant before the
# container image exists.
#
# Usage:
#   1. Update cctv_viewer/config.yaml and CHANGELOG.md.
#   2. Commit the release locally, but do not push main.
#   3. Run: ./scripts/release.sh 0.1.5
#
# The script validates the commit on a temporary branch, publishes the tag and
# waits for GHCR, then advances main. Home Assistant therefore discovers the
# version only after both CI and the container publication have succeeded.
set -eu

RAW_VERSION="${1:-}"
VERSION="${RAW_VERSION#v}"
TAG="v${VERSION}"
RELEASE_BRANCH="release/${TAG}"

if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version>" >&2
  exit 1
fi

if [ "$(git branch --show-current)" != "main" ]; then
  echo "Releases must be created from main." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Commit all release changes before running this script." >&2
  exit 1
fi

CONFIG_VERSION="$(sed -n 's/^version: *"\([^"]*\)"/\1/p' cctv_viewer/config.yaml)"
if [ "$CONFIG_VERSION" != "$VERSION" ]; then
  echo "config.yaml version $CONFIG_VERSION does not match $VERSION." >&2
  exit 1
fi

git fetch origin main
if [ "$(git merge-base HEAD origin/main)" != "$(git rev-parse origin/main)" ]; then
  echo "Local main must be a fast-forward of origin/main." >&2
  exit 1
fi

wait_for_workflow() {
  workflow="$1"
  ref="$2"
  run_id=""
  while [ -z "$run_id" ]; do
    run_id="$(gh run list --workflow "$workflow" --limit 30 \
      --json databaseId,headBranch,headSha \
      --jq ".[] | select(.headBranch == \"$ref\" and .headSha == \"$(git rev-parse HEAD)\") | .databaseId" \
      | head -n 1)"
    [ -n "$run_id" ] || sleep 2
  done

  while :; do
    status="$(gh run view "$run_id" --json status --jq .status)"
    if [ "$status" = "completed" ]; then
      conclusion="$(gh run view "$run_id" --json conclusion --jq .conclusion)"
      if [ "$conclusion" != "success" ]; then
        echo "$workflow failed: https://github.com/robertoamd90/cctv-timeline-viewer/actions/runs/$run_id" >&2
        exit 1
      fi
      break
    fi
    sleep 5
  done
}

echo "Validating $TAG without exposing it on main..."
git push origin "HEAD:refs/heads/${RELEASE_BRANCH}"
wait_for_workflow CI "$RELEASE_BRANCH"

git tag -a "$TAG" -m "CCTV Viewer $VERSION"
git push origin "$TAG"

echo "Waiting for the release workflow to publish $TAG..."
wait_for_workflow Release "$TAG"

git push origin HEAD:main
git push origin --delete "$RELEASE_BRANCH"
echo "Published $TAG and advanced main."
