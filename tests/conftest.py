import os
import tempfile
from pathlib import Path


_TEST_STATE_DIR = Path(tempfile.mkdtemp(prefix="stellar-data-exporter-tests-"))
os.environ.setdefault(
    "STELLAR_EXPORTER_JOB_DB",
    str(_TEST_STATE_DIR / "export-jobs.sqlite3"),
)
os.environ.setdefault(
    "STELLAR_EXPORTER_SCHEDULE_DB",
    str(_TEST_STATE_DIR / "export-schedules.sqlite3"),
)
os.environ.setdefault(
    "STELLAR_EXPORTER_SCHEDULE_KEY_FILE",
    str(_TEST_STATE_DIR / "schedule.key"),
)
os.environ.setdefault("STELLAR_EXPORTER_SCHEDULE_POLL_SECONDS", "3600")
os.environ.setdefault("STELLAR_EXPORTER_UI_AUTH_DISABLED", "1")
