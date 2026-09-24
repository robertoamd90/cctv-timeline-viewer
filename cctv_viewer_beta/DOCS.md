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

## Automatic indexing of today

In **Cameras**, open the general **Automatic indexing — all cameras** section
and enable **Index today in the background**. Set the **Interval (minutes)**
and use **Save automatic indexing**. One global setting covers every camera
using date-partitioned indexing;
automatic indexing is off by default and the suggested interval is 60 minutes.
The accepted range is 1–10080 minutes. Cameras using recursive indexing are
excluded. When upgrading from beta 1, the new global setting starts disabled
at 60 minutes; enable it once to apply it to all supported cameras. Previous
per-camera toggles are no longer used. Recordings and saved events are preserved.

The server runs the schedule even with the browser closed. Enabling it makes
an initial scan due; later runs wait the configured interval after the previous
attempt completes. The scheduler checks due work roughly every ten seconds and
processes cameras sequentially, so busy periods can delay a run. Attempts that
fail, including an offline NAS, also wait the configured interval before retry.
Saved schedules survive restarts; interrupted jobs become eligible again.

Only the **current day's directory in the camera's timezone** is scanned. At
midnight the next due check switches to the new day. Missed days are not caught
up automatically. Open a previous day to refresh its index normally.

Every automatic run still enumerates the filenames in today's directory and
its subdirectories. It inspects metadata and probes only new or unsettled files,
using one probe worker. A file is considered settled after it is observed with
unchanged size and modification time, has a valid duration, and its modification
time is at least two minutes old. This is a stability heuristic, not a file-close
notification: unusual writers that resume after a long pause may require a
normal timeline refresh. Settled files are skipped before explicit metadata
queries; underlying NAS/client directory enumeration can still read metadata.

Automatic scans do not reconcile removals or replacements of settled files.
Opening a day retains the normal full reconciliation (subject to the existing
refresh cache). Interactive partition requests take priority over the next
background job; a scan already running finishes first. The initial scan of a
large day still has to inspect its files, so choose an interval suitable for the
NAS. Logs report listing time, inspected/new/updated file counts and total
indexing time to help assess the load.

Automatic daily indexing also enriches recordings with configured HA events.
It creates no video copies and does not fetch historical days in the background.
Disabling it stops future scheduled scans; an already running scan can finish.
The previous recently-viewed-partition watcher is replaced by these explicit
global settings; `CTV_WATCHER_SECONDS` no longer controls background scans.

## Detection events from Home Assistant

Event enrichment is available in the Home Assistant app through the Supervisor
connection. Standalone and generic Docker deployments can browse recordings,
but do not provide this HA connection automatically. No extra token needs to be
entered in the Home Assistant app.

### Configure each camera

1. Open **Cameras**, select the camera and configure daily partition indexing
   with the directory pattern matching your archive, such as `{YYYY}/{MM}/{DD}`.
2. In the event fields, type part of a sensor's friendly name or entity ID and
   select a result from the dropdown. There is one field each for **Person**,
   **Vehicle**, **Animal**, **Motion** and **Doorbell**, with one entity per field.
3. Use `binary_sensor` entities whose `on` state means the detection is active.
   A camera entity or an HA event entity is not a supported substitute. Leave
   types your camera does not support empty. Use **×** to clear a selection.
4. Choose the video badge position: top-left, top-center, top-right, bottom-left,
   bottom-center or bottom-right. The default is top-right.
5. Select **Save camera**. Sensor selections, removals and badge position apply
   only on save. Select the camera again later to review its saved associations.

The app reads sensor history when it indexes a requested or automatically scheduled day and associates
intervals with that day's recordings. Changing associations makes indexed days
eligible for refresh when requested again. Merely saving a camera does not
collect its entire historical archive. A sensor-list connection error preserves
saved associations: retry after HA connectivity is restored.

### Find and play detections

Timeline clips show an icon for each associated event type. Select an icon to
seek to the first detection of that type in the clip, with up to ten seconds of
lead-in, limited to the clip start. Person uses a moving-person icon; generic
motion uses an abstract motion symbol.

Open **Events** in the timeline toolbar and select one or more types. Selections
use **OR**: Vehicle plus Person includes clips containing either type, as well as
clips containing both. The camera filter still controls which cameras you see.
**Show all**, or clearing every event checkbox, restores all recordings. The
event selection applies to the current page session.

Filtering keeps **whole matching clips**, including footage before and after a
selected detection. Playback skips excluded recordings. When no displayed
camera has a matching clip at the current time, playback jumps to the next
matching clip; cameras without a matching clip remain blank. If nothing matches,
playback stops with a message. Clips without saved matching events are excluded,
even if their footage might contain an undetected or unindexed event.

### Badges and synchronization

Each camera displays badges for its active events over its own video, including
other event types present in a clip selected by the filter. Badges follow the
video timestamp during playback, seeking and speed changes. Known `on`/`off`
intervals determine duration; if the end is missing, the fallback is **three
seconds of recorded time**. These are historical detections displayed during
playback, not new live detection or video analysis.

Badges sit inside the displayed image, excluding black letterbox bars. Small
screens use icons without text. The top-left position leaves room for the camera
name. The mobile toolbar can collapse its date and view controls using the
chevron while keeping playback controls available.

**Recording time offset is already accounted for.** For example, a filename
of `12:00:05` with an Earlier offset of 5 seconds starts on the timeline at
`12:00:00`. An HA detection at `12:00:02` belongs two seconds into that video.
Do not apply the recording offset again to the HA event. This aligns timestamps;
it does not compensate for a sensor's own reporting latency or an incorrect
camera clock. After changing an offset, event associations refresh when the day
is reindexed.

### Historical coverage, retention and backups

HA must still retain the sensor history when a day is first indexed. Opening a
day from five months ago cannot recover events HA has already discarded. Once
associated, events are stored with recording records in CCTV Viewer's SQLite
index and can remain visible after HA history expires. Routine rescans and
temporary HA failures preserve cached events; missing history is not treated as
proof of no activity. Event enrichment currently uses daily partitions, not
recursive indexing, and there is no continuous background event collector.

**Rebuild index deletes saved events**, along with recording records and
thumbnails. Removing a camera or removing its recording records also removes
those events. Reindexing can restore them only if HA still has the history.
Back up the app database before rebuilding if the saved historical events
matter. Camera settings and original videos survive an index rebuild. No second
video archive is created. Beta and stable have separate data: promoting the
software does not migrate cameras or event history between their installations.

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
automatically uses native HLS for compressed playback on iPhone, iPad and other WebKit clients.
On these clients, playback starts after the initial compressed buffer is ready
and transcoding continues incrementally while the recording plays. At 8x and
16x, compressed profiles sample source keyframes to keep transcoding ahead of
playback on lower-power Home Assistant hardware.

## Server resources and recovery

In **Cameras**, administrators can limit concurrent compressed streams and set
an HLS temporary-space budget (256 MiB by default). The stream limit is shared
by all viewers; `0` means unlimited. If capacity is exhausted, reduce the number
of displayed cameras or wait and use the retry action. Pausing and leaving the
page release incomplete compressed sessions. Temporary streaming files do not
create another recording archive. A slow camera can pause the synchronized
group while it buffers, keeping the cameras aligned.

**Hotspot** enlarges one camera. Enable **Auto** to promote cameras according to
recording starts, or select a camera manually. The timeline overview, zoom and
day controls help navigate large archives. Drag the divider above the timeline
to resize it; on mobile, the chevron collapses the secondary toolbar rows.

## Permissions

The app is available only to Home Assistant administrators. Administrators can
add, edit, remove and manually scan cameras, search recordings and load days
from the timeline.

## Data and backups

Camera configuration and the SQLite index are stored in `/data/ctv.db` and are
included in Home Assistant backups. Generated thumbnails are excluded because
they can be regenerated.
