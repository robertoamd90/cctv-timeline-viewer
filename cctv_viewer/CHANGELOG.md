# Changelog

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
