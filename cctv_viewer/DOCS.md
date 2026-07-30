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

## Streaming quality

Open **Stream** in the timeline toolbar to choose a preference for the current
browser:

- **Native** sends the original recording unchanged.
- **Balanced** and **Fast** transcode video on this app before sending it to the
  browser. They are intended for VPN, mobile and slower connections.
- **Metadata** preload minimizes traffic while paused.
- **Automatic** preload can start playback sooner but may use more bandwidth
  and CPU.

Administrators configure the scale percentage, frame rate and maximum bitrate
of Balanced and Fast in the Cameras view. Scaling keeps the original aspect
ratio. High playback speeds are applied during transcoding so client bandwidth
stays close to the selected profile bitrate. Transcoding uses Home Assistant
host CPU; use Native when the client connection is fast enough. CCTV Viewer
automatically uses native HLS delivery on iPhone, iPad and other WebKit clients.
On these clients, playback starts after the initial compressed buffer is ready
and transcoding continues incrementally while the recording plays. At 8x and
16x, compressed profiles sample source keyframes to keep transcoding ahead of
playback on lower-power Home Assistant hardware.

## Permissions

The app is available only to Home Assistant administrators. Administrators can
add, edit, remove and manually scan cameras, search recordings and load days
from the timeline.

## Data and backups

Camera configuration and the SQLite index are stored in `/data/ctv.db` and are
included in Home Assistant backups. Generated thumbnails are excluded because
they can be regenerated.
