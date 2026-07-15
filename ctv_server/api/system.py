import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ctv_server.auth import CurrentUser, current_user, require_admin
from ctv_server.config import deployment_mode, path_within_source_roots, source_roots

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/session")
def session(request: Request):
    user = current_user(request)
    return {
        "deployment": deployment_mode(),
        "authenticated": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "display_name": user.display_name,
        },
        "is_admin": user.is_admin,
        "role_resolved": user.role_resolved,
        "source_roots": list(source_roots()) if user.is_admin else [],
    }


@router.get("/sources/directories")
def list_source_directories(
    request: Request,
    path: Optional[str] = Query(None),
    _: CurrentUser = Depends(require_admin),
):
    roots = source_roots()
    if not roots:
        raise HTTPException(status_code=404, detail="No source roots configured")
    selected = os.path.realpath(os.path.abspath(path or roots[0]))
    if not path_within_source_roots(selected):
        raise HTTPException(status_code=403, detail="Path is outside the configured source roots")
    if not os.path.isdir(selected):
        raise HTTPException(status_code=404, detail="Directory not found")

    entries = []
    try:
        with os.scandir(selected) as iterator:
            for entry in iterator:
                if entry.name.startswith("."):
                    continue
                try:
                    is_directory = entry.is_dir(follow_symlinks=True)
                except OSError:
                    continue
                if not is_directory:
                    continue
                candidate = os.path.realpath(entry.path)
                if path_within_source_roots(candidate):
                    entries.append({"name": entry.name, "path": candidate})
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Directory is not readable") from exc
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Unable to read directory: {exc}") from exc

    entries.sort(key=lambda item: item["name"].casefold())
    root = None
    for candidate_root in roots:
        try:
            if os.path.commonpath((candidate_root, selected)) == candidate_root:
                root = candidate_root
                break
        except ValueError:
            continue
    if root is None:
        raise HTTPException(status_code=403, detail="Path is outside the configured source roots")
    parent = os.path.dirname(selected) if selected != root else None
    return {
        "root": root,
        "path": selected,
        "parent": parent,
        "entries": entries,
    }
