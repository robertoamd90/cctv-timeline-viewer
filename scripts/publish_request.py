#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

import yaml


VERSION_PATTERNS = {
    "stable": re.compile(r"^\d+\.\d+\.\d+$"),
    "beta": re.compile(r"^\d+\.\d+\.\d+-beta\.\d+$"),
}
ADDON_DIRECTORIES = {
    "stable": Path("cctv_viewer"),
    "beta": Path("cctv_viewer_beta"),
}
IMAGES = {
    "stable": "ghcr.io/robertoamd90/cctv-viewer",
    "beta": "ghcr.io/robertoamd90/cctv-viewer-beta",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish a completed image into the Home Assistant catalog."
    )
    parser.add_argument("channel", choices=("stable", "beta"))
    parser.add_argument("image_digest")
    parser.add_argument("source_changelog", type=Path)
    args = parser.parse_args()

    request_path = Path(".release-requests") / f"{args.channel}.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("status") != "pending":
        raise SystemExit(f"{request_path} is not pending")

    version = request["version"]
    if not VERSION_PATTERNS[args.channel].fullmatch(version):
        raise SystemExit(f"Invalid {args.channel} version: {version}")
    if request.get("source_repository") != "robertoamd90/cctv-timeline-viewer-core":
        raise SystemExit("Release request points to an unexpected source repository")
    if not re.fullmatch(r"[0-9a-f]{40}", request.get("source_sha", "")):
        raise SystemExit("Release request has an invalid source SHA")

    addon = ADDON_DIRECTORIES[args.channel]
    config_path = addon / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["version"] = version
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    shutil.copyfile(args.source_changelog, addon / "CHANGELOG.md")

    published_at = datetime.now(timezone.utc).isoformat()
    image = f"{IMAGES[args.channel]}:{version}"
    release = {
        "version": version,
        "status": "published",
        "source_repository": request["source_repository"],
        "source_ref": request["source_ref"],
        "source_sha": request["source_sha"],
        "image": image,
        "image_digest": args.image_digest,
        "published_at": published_at,
    }
    if request.get("candidate"):
        release["candidate"] = request["candidate"]

    state_path = Path("release-state.json")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[args.channel] = release
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    request.update(
        status="published",
        image=image,
        image_digest=args.image_digest,
        published_at=published_at,
    )
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
