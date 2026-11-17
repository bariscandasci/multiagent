"""Komut satırı duman testi."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_command_prints_each_department():
    env = os.environ.copy()
    env["LLM_PROVIDER"] = "openai"
    env["OPENAI_API_KEY"] = ""
    env["GEMINI_API_KEY"] = ""
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, "main.py", "demo"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "BCD TECHNOLOGIES" in output
    assert "Ofis ve altyapı" in output
    assert "Operasyon & Pazar Geliştirme" in output
    assert "Teknik & Ar-Ge" in output
