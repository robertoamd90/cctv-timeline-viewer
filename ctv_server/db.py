import sqlite3
import os
import threading
from collections.abc import Iterable
from contextlib import contextmanager

DB_PATH = os.environ.get("CTV_DB", os.path.expanduser("~/.ctv/ctv.db"))
_WRITE_LOCK = threading.Lock()
RECORDING_TIME_DELTA_SQL = (
    "(COALESCE(c.time_offset_seconds, 0) - COALESCE(r.time_offset_applied_seconds, 0))"
)


def recording_time_delta(row) -> float:
    keys = row.keys()
    configured = row["time_offset_seconds"] if "time_offset_seconds" in keys else 0
    applied = row["time_offset_applied_seconds"] if "time_offset_applied_seconds" in keys else 0
    return (configured or 0) - (applied or 0)


def get_db() -> sqlite3.Connection:
    """Crea una nuova connessione al DB.
    Imposta WAL mode solo se non già attivo (evita lock contention)."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # Controlla se WAL è già attivo prima di settarlo
    row = conn.execute("PRAGMA journal_mode").fetchone()
    if row and row[0].lower() != "wal":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def write_db():
    """Serialize SQLite writers while allowing WAL readers to continue."""
    with _WRITE_LOCK:
        conn = get_db()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_columns(conn: sqlite3.Connection, table: str, definitions: Iterable[str]):
    existing = _columns(conn, table)
    for definition in definitions:
        name = definition.split()[0]
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_db():
    """Inizializza schema DB (idempotente)."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_path TEXT NOT NULL,
            timezone TEXT DEFAULT 'UTC',
            time_offset_seconds REAL NOT NULL DEFAULT 0,
            config TEXT DEFAULT '{}',
            indexing_mode TEXT NOT NULL DEFAULT 'partitioned',
            directory_pattern TEXT NOT NULL DEFAULT '{YYYY}/{MM}/{DD}',
            source_status TEXT NOT NULL DEFAULT 'unknown',
            source_error TEXT,
            last_scan_started REAL,
            last_scan_completed REAL
        );

        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            start_ts REAL NOT NULL,
            end_ts REAL,
            duration REAL,
            codec TEXT,
            resolution TEXT,
            fps REAL,
            size INTEGER,
            mtime REAL,
            hash TEXT,
            thumbnail_path TEXT,
            metadata TEXT DEFAULT '{}',
            partition_key TEXT,
            media_kind TEXT NOT NULL DEFAULT 'video',
            availability TEXT NOT NULL DEFAULT 'available',
            last_seen REAL,
            time_offset_applied_seconds REAL NOT NULL DEFAULT 0,
            UNIQUE(camera_id, path)
        );

        CREATE INDEX IF NOT EXISTS idx_recordings_camera ON recordings(camera_id);
        CREATE INDEX IF NOT EXISTS idx_recordings_start ON recordings(start_ts);
        CREATE INDEX IF NOT EXISTS idx_recordings_range ON recordings(camera_id, start_ts, end_ts);

        CREATE TABLE IF NOT EXISTS partitions (
            camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
            partition_key TEXT NOT NULL,
            path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown',
            error TEXT,
            last_requested REAL,
            last_scanned REAL,
            file_count INTEGER NOT NULL DEFAULT 0,
            progress_done INTEGER NOT NULL DEFAULT 0,
            progress_total INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(camera_id, partition_key)
        );
        CREATE INDEX IF NOT EXISTS idx_partitions_requested ON partitions(last_requested);
    """)
    # Migrazioni additive per database creati dalle versioni PoC.
    _add_columns(conn, "cameras", (
        "time_offset_seconds REAL NOT NULL DEFAULT 0",
        "indexing_mode TEXT NOT NULL DEFAULT 'partitioned'",
        "directory_pattern TEXT NOT NULL DEFAULT '{YYYY}/{MM}/{DD}'",
        "source_status TEXT NOT NULL DEFAULT 'unknown'",
        "source_error TEXT",
        "last_scan_started REAL",
        "last_scan_completed REAL",
    ))
    recording_columns = _columns(conn, "recordings")
    offset_marker_missing = "time_offset_applied_seconds" not in recording_columns
    _add_columns(conn, "recordings", (
        "mtime REAL",
        "partition_key TEXT",
        "media_kind TEXT NOT NULL DEFAULT 'video'",
        "availability TEXT NOT NULL DEFAULT 'available'",
        "last_seen REAL",
        "time_offset_applied_seconds REAL NOT NULL DEFAULT 0",
    ))
    if offset_marker_missing:
        # Beta 0.1.15 stored the then-current camera offset directly in timestamps.
        # Remember that applied value so future reads can compensate without rewriting rows.
        conn.execute("""
            UPDATE recordings
            SET time_offset_applied_seconds = COALESCE(
                (SELECT c.time_offset_seconds FROM cameras c WHERE c.id = recordings.camera_id), 0
            )
        """)
    _add_columns(conn, "partitions", (
        "progress_done INTEGER NOT NULL DEFAULT 0",
        "progress_total INTEGER NOT NULL DEFAULT 0",
    ))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_availability ON recordings(camera_id, availability)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recordings_partition ON recordings(camera_id, partition_key)")
    image_thumbnails = [
        row[0] for row in conn.execute("""
            SELECT thumbnail_path FROM recordings
            WHERE (media_kind = 'image' OR lower(path) LIKE '%.jpg'
                   OR lower(path) LIKE '%.jpeg' OR lower(path) LIKE '%.png')
              AND thumbnail_path IS NOT NULL
        """).fetchall()
    ]
    conn.execute("""
        DELETE FROM recordings
        WHERE media_kind = 'image' OR lower(path) LIKE '%.jpg'
           OR lower(path) LIKE '%.jpeg' OR lower(path) LIKE '%.png'
    """)
    legacy_thumbnails = [
        row[0] for row in conn.execute("""
            SELECT r.thumbnail_path FROM recordings r
            JOIN cameras c ON c.id = r.camera_id
            WHERE c.indexing_mode = 'partitioned' AND r.partition_key IS NULL
              AND r.thumbnail_path IS NOT NULL
        """).fetchall()
    ]
    conn.execute("""
        DELETE FROM recordings
        WHERE partition_key IS NULL
          AND camera_id IN (SELECT id FROM cameras WHERE indexing_mode = 'partitioned')
    """)
    conn.commit()
    conn.close()
    for thumbnail in legacy_thumbnails:
        try:
            os.unlink(thumbnail)
        except OSError:
            pass
    for thumbnail in image_thumbnails:
        try:
            os.unlink(thumbnail)
        except OSError:
            pass
