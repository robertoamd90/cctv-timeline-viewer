# CCTV Timeline Viewer

Browse and synchronize recordings from multiple CCTV cameras on one shared
timeline. CCTV Timeline Viewer is vendor-independent and works with recordings
already available as files on the local filesystem.

## Features

- Synchronized playback across multiple cameras.
- Timeline navigation, zoom, day selection, and configurable camera layouts.
- Efficient day-based indexing for large local, SMB, and NFS archives.
- Read-only access to recordings.
- Home Assistant Ingress support with administrator-only configuration.
- English and Italian user interfaces.

## Home Assistant

Home Assistant OS and Supervised are the primary supported deployments.

1. Open **Settings > Apps > App store > Repositories**.
2. Add this repository:

   ```text
   https://github.com/robertoamd90/cctv-timeline-viewer
   ```

3. Install **CCTV Viewer**, start it, and enable **Show in sidebar**.
4. Configure each camera from the app using a source directory under `/media`.

The repository also exposes **CCTV Viewer Beta** for testing the upcoming
release line. It uses separate app data and the `cctv-viewer-beta` container
image, so it can be installed alongside the stable app without changing it.

The add-on mounts Home Assistant Media read-only. Configure SMB/NFS storage in
Home Assistant first; CCTV Viewer does not mount network shares or store their
credentials. The Home Assistant app is restricted to administrators, who can
configure cameras, request scans and browse recordings.

The published add-on supports `amd64` and `aarch64`. Its SQLite index is stored
under `/data` and included in cold backups. Generated thumbnails are excluded
from backups because they can be rebuilt.

## Standalone

### Requirements

- Python 3.11 or later
- `ffmpeg` and `ffprobe`

```bash
git clone https://github.com/robertoamd90/cctv-timeline-viewer.git
cd cctv-timeline-viewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn ctv_server.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. Use `--reload` only during development.

Standalone mode has no built-in authentication. Use it on a trusted network or
behind an authenticated reverse proxy.

## Docker

```bash
docker build -t cctv-viewer .
docker run --name cctv-viewer -p 8000:8000 \
  -v ctv-data:/root/.ctv \
  -v /mnt/cctv:/sources/cctv:ro \
  cctv-viewer
```

Add cameras with a container-visible path, for example
`/sources/cctv/garage`. The `:ro` mount prevents the application from changing
the original recordings.

## Recording Sources

CCTV Timeline Viewer works with directories visible to its process. SMB and NFS
shares must be mounted by the host before starting the application; FTP is not a
supported source type.

For large or remote archives, configure cameras with the date-partitioned
layout `{YYYY}/{MM}/{DD}`. The app reads only the day directories needed by the
current timeline and keeps a local cache. It does not assume a retention period:
files and days disappear from the index when they no longer exist on the source.

If a camera includes pre-event footage before the timestamp encoded in its file
name, set its **Recording time offset** in seconds. For example, choose
**Earlier (-)** and enter `5` when a file named `12:00:05` starts with footage
from `12:00:00`. Changing the value also adjusts recordings already indexed, so
a full rescan is not required.

Supported recording extensions are MP4, AVI, MKV, MOV, TS, H264, H265, and DAV.
Image files, including JPEG snapshots, are ignored. Browser compatibility still
depends on the actual codec; H.264 video in MP4 or MOV is recommended.

## Repository Layout

```text
ctv_server/    FastAPI backend and SQLite index
ctv_web/       Vanilla JavaScript frontend
cctv_viewer/   Public Home Assistant add-on manifest and documentation
cctv_viewer_beta/ Beta Home Assistant add-on manifest and documentation
scripts/       Development tools
```

There is one application source tree: `ctv_server/` and `ctv_web/`.
`cctv_viewer/config.yaml` is the public Home Assistant add-on manifest, while
the root `repository.yaml` describes the add-on repository itself. GitHub
Actions builds the published multi-architecture image from the root Dockerfile.
The `main` branch is the stable line. The persistent `pre-release` branch is
the beta line; pushes to it publish the beta image. A promotion is done by
opening a pull request from `pre-release` to `main`, then creating a stable
`vX.Y.Z` tag on the merged commit.

For a local Supervisor build without publishing an image, run this from the
repository root:

```bash
./scripts/package-local-addon.sh
```

It generates the ignored `addons/cctv_viewer/` build context. This is a
disposable test artifact, not a second source tree; never edit it manually.

## Development Checks

```bash
python3 -m unittest discover -v
node --check ctv_web/js/i18n.js
node --check ctv_web/js/app.js
node --check ctv_web/js/timeline.js
node --check ctv_web/js/player.js
```

## License

Copyright (C) 2026 robertoamd90.

Licensed under the GNU General Public License v3.0 or later. See [LICENSE](LICENSE).
