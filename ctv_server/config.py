import os
from pathlib import Path


def deployment_mode() -> str:
    value = os.environ.get("CTV_DEPLOYMENT", "standalone").strip().lower()
    return value if value in {"standalone", "homeassistant"} else "standalone"


def is_home_assistant() -> bool:
    return deployment_mode() == "homeassistant"


def home_assistant_admin_only() -> bool:
    value = os.environ.get("CTV_HA_ADMIN_ONLY", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def source_roots() -> tuple[str, ...]:
    raw = os.environ.get("CTV_SOURCE_ROOTS", "/media" if is_home_assistant() else "")
    roots = []
    for value in raw.split(os.pathsep):
        value = value.strip()
        if value:
            roots.append(os.path.realpath(os.path.abspath(value)))
    return tuple(dict.fromkeys(roots))


def trusted_ingress_proxies() -> set[str]:
    raw = os.environ.get("CTV_TRUSTED_PROXIES", "172.30.32.2")
    values = {value.strip() for value in raw.split(",") if value.strip()}
    return values | {"127.0.0.1", "::1"}


def path_within_source_roots(path: str) -> bool:
    roots = source_roots()
    if not roots:
        return True
    candidate = os.path.realpath(os.path.abspath(path))
    for root in roots:
        try:
            if os.path.commonpath((root, candidate)) == root:
                return True
        except ValueError:
            continue
    return False


def display_path(path: str) -> str:
    return str(Path(path))
