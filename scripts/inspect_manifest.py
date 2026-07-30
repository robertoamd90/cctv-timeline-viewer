#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a multi-architecture OCI image index."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    architectures = {
        item.get("platform", {}).get("architecture")
        for item in manifest.get("manifests", [])
    }
    missing = {"amd64", "arm64"} - architectures
    if missing:
        raise SystemExit(f"Image index is missing architectures: {sorted(missing)}")

    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    args.output.write_text(f"digest={digest}\n", encoding="utf-8")
    print(f"Validated amd64 and arm64 as {digest}")


if __name__ == "__main__":
    main()
