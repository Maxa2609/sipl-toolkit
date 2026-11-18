import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))


def test_conformance_suite_passes():
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "conformance", "run_conformance.py")],
                       capture_output=True, text=True, env=env, encoding="utf-8", timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "26/26" in p.stdout


def test_conformance_suite_passes_with_a_legacy_console_encoding():
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="cp1251", PYTHONUTF8="0")
    p = subprocess.run([sys.executable, os.path.join(ROOT, "conformance", "run_conformance.py")],
                       capture_output=True, text=True, env=env, encoding="utf-8", timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
