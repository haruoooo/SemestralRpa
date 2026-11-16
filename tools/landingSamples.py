"""Generates the Big Data landing samples: two real robot executions, one per week (W47, then W48).

Each execution is a separate run of `python -m src.main scheduleImport`, exactly as in production, with:
- the product API in file mode (no server needed);
- a public demo salt, so the published samples never reveal anything about the real LOG_SALT;
- the same salt in both runs, so the same person keeps the same employeeRef across weeks.

Run:  python -m tools.landingSamples
Output: docs/integrations/bigDataDataIntegration/samples/
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tools.sampleSpreadsheets import buildAllSamples

PUBLIC_DEMO_SALT = "foradopico-public-demo-salt"
WEEKS = ("scheduleW47.xlsx", "scheduleW48.xlsx")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    work = root / "data" / "runtime" / "landingSamples"
    target = root / "docs" / "integrations" / "bigDataDataIntegration" / "samples"
    shutil.rmtree(work, ignore_errors=True)
    fixtures = work / "fixtures"
    buildAllSamples(fixtures)
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PRODUCT_API_MODE": "file",
        "FILE_API_OUTPUT_DIR": str(work / "fileApi"),
        "LOG_SALT": PUBLIC_DEMO_SALT,
        "INPUT_DIR": str(work / "input"),
        "REPORT_DIR": str(work / "reports"),
        "LANDING_ZONE_PATH": str(work / "landing"),
        "STATE_DB_PATH": str(work / "state.db"),
        "LOG_DIR": str(work / "logs"),
    }
    (work / "input").mkdir(parents=True)
    for index, fileName in enumerate(WEEKS):  # One execution per week, in order: this is the incremental load
        if index:
            time.sleep(3)  # Distinct execution timestamps, so file names sort in load order
        shutil.copy(fixtures / fileName, work / "input" / fileName)
        completed = subprocess.run([sys.executable, "-m", "src.main", "scheduleImport"], cwd=root, env=environment)
        if completed.returncode != 0:
            print(f"Falha ao importar {fileName} (código {completed.returncode})")
            return completed.returncode
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for batch in sorted((work / "landing" / "schedule").glob("*.json")):
        shutil.copy(batch, target / batch.name)
        print(f"Lote gerado: {target / batch.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
