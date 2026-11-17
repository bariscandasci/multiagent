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
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert "Ayşe Demir" in output
    assert "Deniz Aydın" in output
    assert "3.520.000 TL" in output
    assert "Bulut Host" in output
    assert "worker-01" in output
    assert "kapalı" in output
