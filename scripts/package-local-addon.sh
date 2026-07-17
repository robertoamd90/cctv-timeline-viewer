#!/bin/sh
# Generate the self-contained build context required by a local HA Supervisor build.
#
# Usage (run from this repository root):
#   ./scripts/package-local-addon.sh
#
# The command recreates addons/cctv_viewer and addons/cctv_viewer_beta from the
# canonical source files. Do not edit these directories manually: they are
# generated local test bundles
# and is intentionally ignored by Git.
#
# To test it on Home Assistant, copy the generated directory to the local
# add-on directory on Home Assistant, then rebuild and start the app:
#   <HA local addons directory>/cctv_viewer
#   <HA local addons directory>/cctv_viewer_beta
#
# Public installations do not use this script. They add the GitHub repository
# in Home Assistant and pull the published GHCR image instead.
set -eu

for source in Dockerfile requirements.txt .dockerignore ctv_server ctv_web \
  cctv_viewer cctv_viewer_beta; do
  if [ ! -e "$source" ]; then
    echo "Run this script from the repository root; required source is missing: $source" >&2
    exit 1
  fi
done

for addon in cctv_viewer cctv_viewer_beta; do
  output_dir="addons/$addon"
  rm -rf "$output_dir"
  mkdir -p "$output_dir"

  cp Dockerfile requirements.txt .dockerignore "$output_dir/"
  cp -R ctv_server ctv_web "$output_dir/"
  cp "$addon/CHANGELOG.md" \
     "$addon/DOCS.md" \
     "$addon/README.md" \
     "$addon/apparmor.txt" \
     "$output_dir/"

  # A local add-on is built by Supervisor, so it must not declare a GHCR image.
  awk '!/^image:[[:space:]]/' "$addon/config.yaml" > "$output_dir/config.yaml"
  printf '%s\n' "Local Home Assistant build context generated at: $output_dir"
done
