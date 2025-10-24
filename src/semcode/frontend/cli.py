"""Semi-official launcher that shells out to ``streamlit run`` with config."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..settings import settings


def main() -> None:
    script_path = Path(__file__).with_name("app.py")
    args = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script_path),
        "--server.headless",
        "false",
    ]
    if settings.frontend_port:
        args.extend(["--server.port", str(settings.frontend_port)])
    subprocess.run(args, check=True)
