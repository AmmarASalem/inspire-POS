"""Timestamped backup of inspire.db, safe to run even while the till app is
live (uses SQLite's own backup API instead of a raw file copy, so a backup
can never land mid-write). Prunes anything past KEEP_COUNT so backups don't
grow unbounded on the till's disk.

Run manually:  venv\\Scripts\\python deploy\\windows\\backup_inspire_db.py
Automated:     see backup_inspire_db.bat + CLAUDE.md for Task Scheduler setup.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO_ROOT / "inspire.db"

# Point this at an external drive or cloud-synced folder for real disaster
# recovery — a backup living on the same disk as the original doesn't survive
# that disk failing.
BACKUP_DIR = REPO_ROOT / "backups"
KEEP_COUNT = 14


def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"inspire_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.db"

    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print(f"Backed up {DB_PATH} -> {dest}")

    backups = sorted(BACKUP_DIR.glob("inspire_*.db"))
    for old in backups[:-KEEP_COUNT]:
        old.unlink()
        print(f"Removed old backup {old}")


if __name__ == "__main__":
    main()
