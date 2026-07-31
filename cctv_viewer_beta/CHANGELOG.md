# Changelog

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
