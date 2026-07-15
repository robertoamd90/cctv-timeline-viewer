# CCTV Viewer for Home Assistant

## Installation

1. Add this repository URL to **Settings > Apps > App store > Repositories**.
2. Install and start **CCTV Viewer**.
3. Enable **Show in sidebar** on the app information page.
4. Open CCTV Viewer and, as an administrator, add each camera with the source
   browser rooted at `/media`.

Network storage must first be configured in Home Assistant as Media storage.
The app receives `/media` read-only, so it cannot modify recordings.

## Permissions

Home Assistant administrators can add, edit, remove and manually scan cameras.
Other authenticated users can view every configured camera, search recordings
and load days from the timeline, but cannot change configuration.

## Data and backups

Camera configuration and the SQLite index are stored in `/data/ctv.db` and are
included in Home Assistant backups. Generated thumbnails are excluded because
they can be regenerated.
