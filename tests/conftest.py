import os
import tempfile
from pathlib import Path


_TEST_STATE_DIR = Path(tempfile.mkdtemp(prefix="stellar-data-exporter-tests-"))
os.environ.setdefault(
    "STELLAR_EXPORTER_JOB_DB",
    str(_TEST_STATE_DIR / "export-jobs.sqlite3"),
)
