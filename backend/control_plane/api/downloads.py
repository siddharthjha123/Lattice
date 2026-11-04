"""A fixed, secret-free worker release; no arbitrary filesystem access."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()
WHEEL = "lattice-0.3.2-py3-none-any.whl"
RESTART_WHEEL = "lattice-0.3.1-py3-none-any.whl"
WINDOWS_WHEEL = "lattice-0.3.0-py3-none-any.whl"
PREVIOUS_WHEEL = "lattice-0.2.0-py3-none-any.whl"


@router.get("/downloads/" + PREVIOUS_WHEEL, include_in_schema=False)
@router.get("/downloads/" + WINDOWS_WHEEL, include_in_schema=False)
@router.get("/downloads/" + RESTART_WHEEL, include_in_schema=False)
@router.get("/downloads/" + WHEEL, include_in_schema=False)
async def worker_release(request: Request):
    directory = request.app.state.context.config.WORKER_RELEASE_DIR
    name = request.url.path.rsplit("/", 1)[-1]
    if name not in {WHEEL, RESTART_WHEEL, WINDOWS_WHEEL, PREVIOUS_WHEEL}:
        raise HTTPException(404, "Unknown worker release")
    path = directory / name if directory else None
    if path is None or not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Worker release not installed on this controller")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
        headers={"Cache-Control": "no-cache"},
    )
