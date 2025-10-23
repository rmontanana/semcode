"""
Console entry point that launches the Streamlit UI using Streamlit's CLI runner.
"""
from __future__ import annotations

from pathlib import Path

from streamlit.web import cli as stcli

from ..settings import settings


def main() -> None:
    script_path = Path(__file__).with_name("app.py")
    args = [
        "streamlit",
        "run",
        str(script_path),
        "--server.headless",
        "false",
    ]
    if settings.frontend_port:
        args.extend(["--server.port", str(settings.frontend_port)])
    stcli.main_run(args)
