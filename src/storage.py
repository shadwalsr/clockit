"""
GhostTrack Storage Module
Local storage system for managing snapshots and run metadata.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

SNAPSHOTS_DIR = Path('snapshots')
LAST_RUN_FILE = Path('last_run.json')
TOOL_VERSION = '2.0'


def save_snapshot(account: str, followers: list, following: list, fetch_duration: float) -> Path:
    """
    Save a snapshot of the current followers/following state.

    Creates the snapshots directory if needed and writes a JSON file with
    the schema: {timestamp, account, followers, following, fetch_duration_seconds, tool_version}.

    Returns the path to the saved snapshot file.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    filename = f"snapshot_{now.strftime('%Y%m%d_%H%M')}.json"
    filepath = SNAPSHOTS_DIR / filename

    snapshot_data = {
        'timestamp': now.isoformat(),
        'account': account,
        'followers': sorted(followers),
        'following': sorted(following),
        'fetch_duration_seconds': round(fetch_duration, 1),
        'tool_version': TOOL_VERSION,
    }

    filepath.write_text(json.dumps(snapshot_data, indent=2), encoding='utf-8')
    console.print(f"[green]Snapshot saved:[/green] {filepath}")
    return filepath


def update_last_run() -> None:
    """
    Update the 'last_run' field in last_run.json with the current ISO timestamp.
    Handles missing or corrupt existing files gracefully.
    """
    data = {}
    if LAST_RUN_FILE.exists():
        try:
            data = json.loads(LAST_RUN_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            console.print("[yellow]Warning:[/yellow] last_run.json was corrupt, resetting.")
            data = {}

    data['last_run'] = datetime.now(timezone.utc).isoformat()
    LAST_RUN_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')


def update_deactivation_check_timestamp() -> None:
    """
    Update the 'last_deactivation_check' field in last_run.json with the current ISO timestamp.
    Handles missing or corrupt existing files gracefully.
    """
    data = {}
    if LAST_RUN_FILE.exists():
        try:
            data = json.loads(LAST_RUN_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, ValueError):
            console.print("[yellow]Warning:[/yellow] last_run.json was corrupt, resetting.")
            data = {}

    data['last_deactivation_check'] = datetime.now(timezone.utc).isoformat()
    LAST_RUN_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')


def load_snapshots() -> list:
    """
    Load all snapshot files from the snapshots directory.

    Returns a list of parsed snapshot dicts sorted by filename descending
    (most recent first). Each dict includes an '_filepath' key with the
    path to the source file. Warns on corrupt files and skips them.
    """
    if not SNAPSHOTS_DIR.exists():
        return []

    snapshot_files = sorted(
        SNAPSHOTS_DIR.glob('snapshot_*.json'),
        key=lambda p: p.name,
        reverse=True,
    )

    snapshots = []
    for filepath in snapshot_files:
        try:
            data = json.loads(filepath.read_text(encoding='utf-8'))
            data['_filepath'] = str(filepath)
            snapshots.append(data)
        except (json.JSONDecodeError, ValueError) as e:
            console.print(f"[yellow]Warning:[/yellow] Corrupt snapshot file skipped: {filepath} ({e})")

    return snapshots


def load_latest_snapshot() -> Optional[dict]:
    """
    Load the most recent snapshot.

    Returns the latest snapshot dict, or None if no snapshots exist.
    """
    snapshots = load_snapshots()
    return snapshots[0] if snapshots else None


def load_previous_snapshot() -> tuple:
    """
    Load the second-most-recent snapshot for diffing.

    Returns a tuple of (snapshot_dict_or_None, is_stale_bool).
    is_stale is True if the snapshot's timestamp is more than 30 days old.
    Returns (None, False) if fewer than 2 snapshots exist.
    """
    snapshots = load_snapshots()
    if len(snapshots) < 2:
        return (None, False)

    previous = snapshots[1]
    is_stale = False

    try:
        snapshot_time = datetime.fromisoformat(previous['timestamp'])
        # Ensure timezone-aware comparison
        now = datetime.now(timezone.utc)
        if snapshot_time.tzinfo is None:
            snapshot_time = snapshot_time.replace(tzinfo=timezone.utc)
        age_days = (now - snapshot_time).days
        is_stale = age_days > 30
    except (KeyError, ValueError, TypeError):
        # If timestamp is missing or unparseable, treat as not stale
        is_stale = False

    return (previous, is_stale)
