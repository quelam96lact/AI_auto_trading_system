"""Unit tests for scripts/research188_validate.py on synthetic data."""

import csv
import gzip
import hashlib
import subprocess
import sys
from pathlib import Path

from scripts.research188_validate import compute_sha256


def _write_gz(path: Path, rows: list[list[str]]) -> str:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_validator_sha_mismatch_returns_2(tmp_path: Path):
    """Validator must return exit code 2 when candidates.json sha256 does not match."""
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]", encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "scripts.research188_validate",
        "--data-dir",
        str(tmp_path),
        "--candidates",
        str(cand_file),
        "--candidates-sha",
        "wrong_sha_hash",
        "--part",
        "V1",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 2
    assert "candidates sha mismatch" in res.stderr


def test_validator_missing_data_returns_3(tmp_path: Path):
    """Validator must return exit code 3 when data dir is invalid."""
    cand_file = tmp_path / "candidates.json"
    cand_file.write_text("[]", encoding="utf-8")
    actual_sha = compute_sha256(cand_file)

    cmd = [
        sys.executable,
        "-m",
        "scripts.research188_validate",
        "--data-dir",
        str(tmp_path / "non_existent_dir"),
        "--candidates",
        str(cand_file),
        "--candidates-sha",
        actual_sha,
        "--part",
        "V1",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 3
