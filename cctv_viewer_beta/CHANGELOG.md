# Changelog

## 0.1.30

### Optional current-day automatic indexing

- Configure background indexing and its interval once for all date-partitioned
  cameras in general settings. Default off, with a 60-minute interval and a
  dedicated Save automatic indexing action.
- Replace beta 1 per-camera controls. On upgrade the new global policy starts
  disabled; saved recordings and events are preserved.
- Scan only the current day in each camera’s timezone, even with no browser open.
  Preserve schedules across restart and recover interrupted partition jobs.
- List filenames but skip metadata reads and probing for confirmed stable files;
  retry new or growing files and failed duration probes using one probe worker.
- Serialize partition scans and prioritize interactive requests. Retain full
  reconciliation when a day is opened, without background historical scans.
- Associate HA events during scheduled scans, respect retry intervals on NAS
  failures, and log indexing workload and timing.
- Replace the implicit recently-viewed-partition watcher with explicit schedules.

## 0.1.29

### Home Assistant detection events

- Associate one Home Assistant binary sensor per camera and event type: person,
  vehicle, animal, motion and doorbell. Search by name or entity ID, select a
  result, clear it with × and apply changes with Save camera. Reopening a camera
  shows its saved associations; discovery failures preserve those settings.
- Fetch HA history during daily partition indexing and store detections on the
  existing recording records, without copying videos or collecting live events.
  Keep cached events across ordinary rescans and temporary HA failures.
- Associate events using the camera's recording time offset. Preserve intervals
  spanning multiple recordings and refresh older cached events for duration
  information when history remains available.
- Show event icons on timeline clips. Select an icon to seek to the first event
  of that type with up to ten seconds of lead-in within the recording.

### Event filtering and synchronized playback

- Filter whole recordings by one or more event types. Multiple selections use
  OR matching: vehicle and person includes clips with either detection.
- Apply the same filter to playback and camera selection. Skip excluded clips
  and gaps across displayed cameras; leave a camera blank when it has no
  matching recording. Show feedback when no clips match.
- Display event badges over each camera's video for the recorded on/off
  interval, with a three-second fallback when the end is unknown. Badges follow
  seeking and accelerated playback, rather than elapsed wall-clock time.
- Save one of six badge positions per camera: top or bottom, left, center or
  right. Use distinct person and generic motion icons.

### Mobile usability and reliability

- Keep badges eight pixels inside the displayed image, reserving clearance for
  the camera label in the top-left corner; show compact icon-only badges on
  small screens.
- Keep all five mobile view controls on one row without overlapping buttons or
  an extra Auto Hotspot row.
- Refresh thumbnails as background generation completes, discard stale timeline
  responses and refresh indexed days after sensor associations change.
- Fix HA discovery and history access through the Supervisor proxy, including
  AppArmor DNS resolver access, and report specific connection failure codes.

### Historical data requirements

- Event enrichment requires daily partition indexing and HA binary-sensor
  history still available when the day is indexed. Missing history is unknown
  coverage, not proof that no detections occurred.
- Stored events remain available with their recording records after HA history
  expires. Rebuilding the index or deleting those records removes their events;
  they can only be recovered if HA still retains the corresponding history.

## 0.1.28

### Remote playback efficiency

- Preserve aligned MP4 streams during buffering and restart only cameras that
  need realignment. Use separate running and recovery buffer thresholds to
  reduce repeated short pauses on limited bandwidth.
- Ignore obsolete playback responses after seeking or changing sources. Bound
  recovery attempts and show an explicit message with a retry action.
- Add a shared, configurable MP4/HLS transcoder limit in the Cameras view,
  admitting sessions before starting video delivery and releasing capacity
  when encoding finishes or playback is cancelled.
- Release incomplete compressed streams after a short pause grace period and
  when leaving the page; reuse fully downloaded MP4 buffers on resume.
- Add a configurable HLS temporary-space budget, defaulting to 256 MiB, with
  explicit session invalidation when the budget is exceeded. No additional
  recording archive or persistent video copies are created.
- Remove HLS input pacing at 8x/16x to avoid delayed startup after seeks, and
  fix native HLS playback of very short clip tails before the next recording.
- Add bounded playback diagnostics and synthetic benchmark tools for field
  investigation without scanning or duplicating the surveillance archive.

## 0.1.27

### Partition-aware timeline index

- Detach the R-Tree write triggers from early betas before any recording
  maintenance, leaving the unused virtual table untouched so even a damaged
  optional index cannot block scans or rebuilds.
- Query the exact daily partitions through an ordinary composite SQLite index,
  matching the application's one-day timeline workflow without virtual tables.
- Keep rebuild independent from derived data and report SQLite extended error
  names, codes and the failing scan stage when database operations fail.

### Home Assistant database recovery

- Direct SQLite temporary files to the AppArmor-authorized `/tmp` directory;
  SQLite otherwise prefers `/var/tmp`, which the application sandbox denies.
- Reconcile removed recordings with single-row statements so large scans do not
  require a disk-backed statement journal.
- Delete camera data and rebuild the archive through bounded single-row
  operations, keeping both recovery actions usable under Home Assistant.
- Make partition thumbnail workers cancellable derived work, preventing them
  from leaving Rebuild index permanently blocked after a scan.
- Return to short-lived SQLite connections instead of retaining an idle WAL
  connection across the complete server lifetime.

### Large archive performance

- Add partition-aware composite indexes for timeline and time-bounded search
  queries while retaining exact camera-offset and overlap semantics.
- Maintain camera availability counters incrementally and use indexed boundary
  lookups instead of aggregating the complete recordings table.
- Cache streaming profiles to remove repeated database work from hot paths.

### Playback resource control

- Pace mobile HLS generation slightly ahead of playback instead of encoding
  the entire remainder of every camera recording as fast as possible.
- Give each simultaneous decoder, filter graph and H.264 encoder one CPU
  thread, preventing three-camera mobile playback from multiplying into
  unrestricted multi-core FFmpeg workloads.
- Cancel mobile HLS jobs immediately when a stream is replaced, playback is
  paused or the page closes, with a server-side idle watchdog for abandoned
  clients.
- Restrict background thumbnail decoding, filtering and encoding to one thread
  so indexing cannot starve active video delivery.

### Timeline rendering

- Aggregate progress across simultaneous camera partitions and keep each
  counter monotonic when delayed events arrive out of order.
- Reset progress before retrying a partition, so a missing future day cannot
  briefly display file counts left by an earlier failed scan.
- Index recording intervals in the browser for fast visible-window and Auto
  Hotspot selection on densely populated timelines.
- Cache the overview canvas, delegate segment hover handling, coalesce panning
  renders and load timeline thumbnails lazily.
- Avoid repeated media-buffer and absolute-time calculations during playback
  synchronization frames.

### Indexing efficiency and validation

- Recover video duration from stream metadata when the container omits it and
  report ffprobe failures instead of silently indexing zero-length segments.
- Bust native-video URLs after a reload and recover from stale browser byte
  ranges when rebuilt databases reuse recording IDs, preventing persistent 416
  playback failures.
- Reconcile missing recordings with set-based SQL, bound concurrent metadata
  probes and scan directories through `scandir` to reduce CPU, memory and
  database work on large sources.
- Add repeatable backend, indexer and frontend performance benchmarks together
  with randomized equivalence, migration and interval-boundary regression tests.

## 0.1.26

### Mobile viewing

- Let mobile users collapse the date and view-control rows while keeping the
  primary playback controls available, remember the compact preference and
  keep the toggle inside the first control row without covering the video.
- Keep mobile control heights consistent by preventing the Auto Hotspot
  checkbox from expanding its toolbar row.
### Playback performance and cleanup

- Stop abandoned progressive FFmpeg transcodes when a client no longer consumes
  output, and terminate any remaining progressive jobs during server shutdown.
- Reduce playback UI work by throttling clock rendering while keeping the
  synchronization state machine on every animation frame.
- Move the overview playhead independently instead of redrawing every timeline
  segment throughout playback.
- Use binary lookup for the active recording, keeping segment selection fast on
  densely populated days.

### Indexing efficiency

- Reserve partition scans atomically so concurrent clients cannot enqueue the
  same remote-directory scan multiple times.
- Apply the partition refresh interval to missing day directories, avoiding
  repeated filesystem and database work while still detecting them later.

## 0.1.25

### Desktop compressed playback

- Route Balanced and Fast playback through progressive MP4 on desktop browsers,
  avoiding unreliable native HLS behavior reported by Chrome and Firefox.
- Keep transcoded streams active behind the shared freeze frame while they
  accumulate enough data to resume synchronized playback.
- Preserve native HLS delivery on touch devices, where it remains the reliable
  transport for mobile playback.
- Prevent the buffering barrier from remaining permanently stuck on
  "Source connection is slow" after the first compressed segment.

### Playback transitions

- Apply speed changes immediately to the current Native recording and preserve
  the selected rate through later buffering barriers.
- Let a parallel camera continue uninterrupted when another camera reaches the
  end of its recording.
- Reopen progressive streams from the authoritative timeline timestamp instead
  of seeking inside non-seekable transcoded MP4 output.
- Decode arbitrary high-speed offset starts normally when keyframe-only
  decoding would produce an empty tail segment.
- Complete very short MP4 tails inside the buffering barrier without replaying
  them from zero.
- Size the startup buffer from the browser's actual media consumption rate,
  avoiding a deadlock that could occur after a speed or quality change.
- Skip compressed recording tails that are too short to produce a single
  output frame, instead of surfacing a random demux or unplayable-file error.

## 0.1.24

### Adaptive streaming

- Add Native, Balanced and Fast quality modes for local, VPN and mobile
  connections.
- Let administrators configure scale percentage, frame rate and maximum bitrate
  for Balanced and Fast while preserving each recording's aspect ratio.
- Apply accelerated playback during transcoding so client bandwidth remains
  bounded by the selected profile, including at 8x and 16x.
- Add per-browser Metadata and Automatic preload preferences to balance startup
  latency against network and CPU usage.

### Mobile playback

- Deliver compressed streams as native HLS on iPhone, iPad and other WebKit
  clients while retaining fragmented MP4 on compatible browsers.
- Start playback as soon as the initial HLS buffer is ready and continue
  transcoding incrementally instead of waiting for the complete recording.
- Align HLS timestamps to zero and anchor playback to the recording start,
  preventing repeated seeks and moving-live-edge behavior on mobile browsers.
- Clean up generated HLS segments automatically after playback.

### Synchronization and reliability

- Start active cameras behind a shared seek and buffering barrier and derive the
  playback clock from their median timestamp.
- Pause and realign the complete camera group when one stream falls behind,
  rather than allowing cameras to drift apart.
- Keep the last decoded frame visible while buffering and prevent completed
  warm-up clips from skipping through later recordings.
- Recenter the timeline immediately when playback crosses a large recording
  gap and clear loading feedback as soon as a selected frame is ready.

### High-speed performance

- Decode keyframes only for compressed 8x and 16x playback, reducing transcoder
  CPU pressure while keeping full-frame decoding from 1x through 4x.
- Scale the required startup buffer with effective timeline speed and prepare
  four HLS segments before starting compressed 8x and 16x playback.
- Hold every active camera at the synchronization barrier without consuming its
  prepared buffer, improving recovery when several cameras become active at
  once.
- Add HLS startup, completion, timeout and FFmpeg failure diagnostics.

## 0.1.12

- Improve the Auto Hotspot control layout and labeling on mobile screens.
- Correct invalid fragmented-MP4 duration metadata while streaming, without modifying or transcoding source files.
- Stabilize Firefox playback and clip transitions for camera-generated MP4 files.
- Avoid visible frame rewinds during buffering warm-up.
- Reduce artificial global buffering during high-speed camera synchronization.
- Prevent playback from stalling on the final frames of a recording.

## 0.1.6

- Keep timeline previews inside the visible viewport.
- Add an explicit Auto Hotspot toggle.
- Promote the camera whose segment starts most recently during playback.
- Return to manual hotspot selection when the user chooses a camera.

## 0.1.5

- Replace free-text camera timezones with an IANA timezone selector.
- Preselect the browser timezone for new cameras.
- Suggest the camera name from the selected source directory.
- Add a release helper that publishes images before exposing updates to Home Assistant.

## 0.1.4

- Allow the source browser to read the `/media` root directory under AppArmor.

## 0.1.3

- Restore the Cameras administration panel for Home Assistant administrators.
- Let Home Assistant enforce administrator access at the Ingress panel boundary.

## 0.1.2

- Install the backend package into the container Python environment.
- Remove runtime dependency on the container working directory and `PYTHONPATH`.
- Add a container smoke test for the Home Assistant runtime environment.

## 0.1.0

- Initial Home Assistant App release.
- Ingress sidebar UI with streamed video and realtime progress.
- Read-only Home Assistant Media access.
- Administrator configuration and read-only viewer roles.
