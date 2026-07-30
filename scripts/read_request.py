#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Expose release request fields.")
    parser.add_argument("channel", choices=("stable", "beta"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    request_path = Path(".release-requests") / f"{args.channel}.json"
    if not request_path.is_file():
        args.output.write_text("pending=false\n", encoding="utf-8")
        return

    request = json.loads(request_path.read_text(encoding="utf-8"))
    pending = request.get("status") == "pending"
    lines = [f"pending={'true' if pending else 'false'}"]
    if pending:
        for key in ("version", "source_sha", "source_ref", "candidate"):
            value = request.get(key, "")
            if "\n" in value:
                raise SystemExit(f"Invalid newline in request field {key}")
            lines.append(f"{key}={value}")
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
