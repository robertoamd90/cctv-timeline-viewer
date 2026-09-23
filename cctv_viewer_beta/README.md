# CCTV Viewer

Browse existing surveillance recordings on a synchronized multi-camera timeline.
CCTV Viewer reads Home Assistant Media without modifying the original files or
creating a second video archive.

- Day-based indexing for large archives, timeline thumbnails and camera filters.
- Grid and Hotspot layouts, automatic camera promotion and compact mobile controls.
- Native, Balanced and Fast playback for local and bandwidth-limited connections.
- Searchable HA binary-sensor associations for person, vehicle, animal, motion
  and doorbell events, saved separately for each camera.
- Event filters that skip excluded clips during playback, and timed video badges
  with six configurable positions per camera.
- English and Italian interfaces.

Start the app, enable **Show in sidebar**, and configure cameras as a Home
Assistant administrator. Configure network storage as Media storage first.

See the **Documentation** tab for setup, event history requirements, time-offset
examples and resource settings. Events require daily partition indexing and
history still retained by HA when the day is indexed. Rebuilding the index
removes saved events; original recordings and camera settings are preserved.

Stable and Beta installations use separate app data. Updating the stable app
does not import a Beta installation's settings or historical events.
