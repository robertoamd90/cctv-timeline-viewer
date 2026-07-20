# Changelog

## 0.1.14

- Start all active cameras only after a shared seek and buffering barrier.
- Derive the playback clock from the median camera timestamp instead of the first camera.
- Pause and realign the complete camera group when timestamps diverge.

## 0.1.13

- Clear the loading state as soon as a selected frame is ready, even while playback is paused.
- Recenter the visible timeline immediately when playback skips across a large recording gap.
- Keep the last decoded frame visible during buffering warm-up to prevent black flashes.

## 0.1.12

- Correct invalid fragmented-MP4 duration metadata while streaming, without modifying or transcoding source files.
- Remove the Firefox loading workaround that could alternate between old and current frames.
- Avoid artificial global buffering during routine high-speed camera synchronization.
- Prevent playback from stalling on the final frames of a recording.

## 0.1.11

- Fix playback of camera MP4 files whose duration grows progressively in Firefox.
- Use indexed recording duration instead of transient browser duration for seeking and completion.
- Keep progressive media loading during synchronization barriers to prevent Firefox buffering deadlocks.

## 0.1.10

- Fix timeline playback on Firefox by seeking only after media metadata is available.
- Prevent transient loading and stalled events from being interpreted as the end of a recording.
- Retry an unexpected early media end instead of skipping the recording.

## 0.1.9

- Keep the full Auto Hotspot label on mobile when space is available.
- Truncate the label with an ellipsis on narrower screens without changing the toolbar height.
- Expose the complete label through the control title and accessibility metadata.

## 0.1.8

- Place the Auto Hotspot toggle in the mobile view-controls row.
- Keep the full Auto Hotspot label on desktop and use a compact mobile label.

## 0.1.7

- Preview channel for upcoming CCTV Viewer features.

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
