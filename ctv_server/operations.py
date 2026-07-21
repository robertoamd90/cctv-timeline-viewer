import threading
from contextlib import contextmanager
from typing import Optional


class IndexBusyError(RuntimeError):
    pass


_guard = threading.Lock()
_active_index_jobs = 0
_maintenance_active = False
_index_generation = 0


def index_generation() -> int:
    with _guard:
        return _index_generation


def begin_index_job(expected_generation: Optional[int] = None) -> bool:
    global _active_index_jobs
    with _guard:
        if _maintenance_active or (
            expected_generation is not None and expected_generation != _index_generation
        ):
            return False
        _active_index_jobs += 1
        return True


def end_index_job():
    global _active_index_jobs
    with _guard:
        _active_index_jobs = max(0, _active_index_jobs - 1)


@contextmanager
def maintenance_window():
    global _index_generation, _maintenance_active
    with _guard:
        if _maintenance_active or _active_index_jobs:
            raise IndexBusyError("Indexing is in progress")
        _maintenance_active = True
        _index_generation += 1
    try:
        yield
    finally:
        with _guard:
            _maintenance_active = False
