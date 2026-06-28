"""Auto-backup for SuperEzio databases. Run via cron/scheduled task."""
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

BACKUP_DIR = Path("data/backups")
DB_FILES = [
    "data/historical_cache.db",
    "data/expert_analyses.db",
    "data/paper_journal.jsonl",
]
MAX_BACKUPS = 7  # Keep last 7 daily backups


def backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    backup_subdir = BACKUP_DIR / date_str
    backup_subdir.mkdir(exist_ok=True)

    for db_path in DB_FILES:
        src = Path(db_path)
        if not src.exists():
            continue
        dst = backup_subdir / src.name
        try:
            if src.suffix == ".db":
                # SQLite: use backup API for consistency
                src_conn = sqlite3.connect(str(src))
                dst_conn = sqlite3.connect(str(dst))
                src_conn.backup(dst_conn)
                src_conn.close()
                dst_conn.close()
            else:
                shutil.copy2(src, dst)
        except Exception as e:
            print(f"  ERROR backing up {src.name}: {e}")

    # Cleanup old backups
    existing = sorted(BACKUP_DIR.glob("20*"))
    for old in existing[:-MAX_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
        print(f"  Removed old backup: {old}")

    print(f"Backup complete: {backup_subdir}")


if __name__ == "__main__":
    backup()
