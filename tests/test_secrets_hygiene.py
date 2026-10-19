"""Tracked files hold no Kafka credentials or credential patterns (AC-29).

Reads only the process environment, never a ``.env`` file: when the broker host, SASL user or
password are exported in the shell, their values must not appear in any file git would commit.
Without them the generic patterns still run.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve().relative_to(ROOT).as_posix()
SECRET_ENV_VARS = ("KAFKA_BOOTSTRAP", "KAFKA_USERNAME", "KAFKA_PASSWORD")
MIN_SECRET_LENGTH = 6  # shorter values would match too much text to be a useful scan

# Generic credential patterns. Each needs a literal value, so names and placeholders pass.
PATTERNS = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Databricks token": re.compile(r"\bdapi[0-9a-f]{32}\b"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "password literal": re.compile(
        r"""(?i)\b(?:password|passwd|sasl_password)\s*[=:]\s*["'][^"'\s${}<>]{6,}["']"""
    ),
    "secret or token literal": re.compile(
        r"""(?i)\b(?:secret|api_key|access_token|auth_token)\s*[=:]\s*["'][A-Za-z0-9+/_\-]{16,}["']"""
    ),
    "service URI with credentials": re.compile(r"[a-z]+://[^/\s:@]+:[^/\s:@]{4,}@[^/\s]+"),
}
# Files that legitimately describe credential formats.
ALLOWED = {THIS_FILE, ".env.example"}


def tracked_files() -> list[Path]:
    """Files git tracks, plus new files that are not ignored (they would be committed next)."""
    out = subprocess.run(  # noqa: S603
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],  # noqa: S607
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode()
    paths = [ROOT / name for name in out.split("\0") if name]
    return [p for p in paths if p.is_file()]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def test_ac29_tracked_files_contain_no_kafka_credentials() -> None:
    values = {
        name: os.environ[name]
        for name in SECRET_ENV_VARS
        if len(os.environ.get(name, "")) >= MIN_SECRET_LENGTH
    }
    offenders: list[str] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED:
            continue
        text = read_text(path)
        if text is None:
            continue
        for name, value in values.items():
            if value in text:
                offenders.append(f"{rel}: value of {name}")  # the value itself is never printed
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                offenders.append(f"{rel}: {label}")
    assert not offenders, "credential-like content in tracked files:\n" + "\n".join(offenders)


def test_ac29_env_files_and_keys_are_not_tracked() -> None:
    names = [p.relative_to(ROOT).as_posix() for p in tracked_files()]
    assert ".env" not in names
    assert not [n for n in names if n.endswith((".pem", ".key", ".p12", ".jks"))]
    assert not [n for n in names if Path(n).name.startswith(".env") and n != ".env.example"]


def test_ac29_env_example_has_no_values_for_secret_variables() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() in {"KAFKA_PASSWORD", "KAFKA_USERNAME", "KAFKA_BOOTSTRAP"}:
            assert value.strip() == "", f"{key.strip()} must have no value in .env.example"


@pytest.mark.parametrize(
    ("label", "sample"),
    [
        ("private key block", "-----BEGIN " + "RSA PRIVATE" + " KEY-----"),
        ("password literal", 'password = "hunter2hunter2"'),
        ("Databricks token", "dapi" + "0123456789abcdef" * 2),
        ("service URI with credentials", "kafka://user:abcd1234@broker.example"),
    ],
)
def test_ac29_patterns_detect_planted_credentials(label: str, sample: str) -> None:
    assert PATTERNS[label].search(sample)


def test_ac29_patterns_ignore_names_and_placeholders() -> None:
    clean = 'sasl_password = os.environ["KAFKA_PASSWORD"]\npassword: "${secret}"\nsecret_scope = x'
    assert not [label for label, pattern in PATTERNS.items() if pattern.search(clean)]
