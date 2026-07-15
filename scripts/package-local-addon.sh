#!/bin/sh
# Generate the self-contained build context required by a local HA Supervisor build.
#
# Usage (run from this repository root):
#   ./scripts/package-local-addon.sh
#
# The command recreates addons/cctv_viewer from the canonical source files:
#   ctv_server/, ctv_web/, Dockerfile, requirements.txt and cctv_viewer/.
# Do not edit addons/cctv_viewer manually: it is a generated local test bundle
# and is intentionally ignored by Git.
#
# To test it on Home Assistant, copy the generated directory to the local
# add-on directory on Home Assistant, then rebuild and start the app:
#   <HA local addons directory>/cctv_viewer
#
# Public installations do not use this script. They add the GitHub repository
# in Home Assistant and pull the published GHCR image instead.
set -eu

OUTPUT_DIR="addons/cctv_viewer"

for source in Dockerfile requirements.txt .dockerignore \
  ctv_server ctv_web \
  cctv_viewer/CHANGELOG.md cctv_viewer/DOCS.md cctv_viewer/README.md \
  cctv_viewer/apparmor.txt cctv_viewer/config.yaml; do
  if [ ! -e "$source" ]; then
    echo "Run this script from the repository root; required source is missing: $source" >&2
    exit 1
  fi
done

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

cp Dockerfile requirements.txt .dockerignore "$OUTPUT_DIR/"
cp -R ctv_server ctv_web "$OUTPUT_DIR/"
cp cctv_viewer/CHANGELOG.md \
   cctv_viewer/DOCS.md \
   cctv_viewer/README.md \
   cctv_viewer/apparmor.txt \
   "$OUTPUT_DIR/"

# A local add-on is built by Supervisor, so it must not declare the GHCR image.
awk '!/^image:[[:space:]]/' cctv_viewer/config.yaml > "$OUTPUT_DIR/config.yaml"

printf '%s\n' "Local Home Assistant build context generated at: $OUTPUT_DIR"
