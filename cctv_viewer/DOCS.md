# CCTV Viewer for Home Assistant

## Installation

1. Add this repository URL to **Settings > Apps > App store > Repositories**.
2. Install and start **CCTV Viewer**.
3. Enable **Show in sidebar** on the app information page.
4. Open CCTV Viewer and, as an administrator, add each camera with the source
   browser rooted at `/media`.

Network storage must first be configured in Home Assistant as Media storage.
The app receives `/media` read-only, so it cannot modify recordings.

For cameras that include footage preceding the timestamp in the filename, use
the per-camera **Recording time offset**. Choose **Earlier (-)** and enter `5`,
for example, when a file named `12:00:05` actually begins at `12:00:00`.
Existing indexed recordings are adjusted immediately and do not need to be
scanned again.

The administrator-only **Rebuild index** action removes the local recording
index, loaded day partitions and generated thumbnails while preserving camera
settings and original files. Days are indexed again when requested from the
timeline.

## Permissions

The app is available only to Home Assistant administrators. Administrators can
add, edit, remove and manually scan cameras, search recordings and load days
from the timeline.

## Data and backups

Camera configuration and the SQLite index are stored in `/data/ctv.db` and are
included in Home Assistant backups. Generated thumbnails are excluded because
they can be regenerated.
