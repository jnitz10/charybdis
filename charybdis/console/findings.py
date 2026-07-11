"""Curated overview content, hand-written in findings.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_findings() -> dict:
    return yaml.safe_load((Path(__file__).with_name("findings.yaml")).read_text())
