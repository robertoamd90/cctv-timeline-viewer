# Changelog

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
