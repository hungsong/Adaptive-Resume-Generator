# -*- coding: utf-8 -*-
"""让 pytest 能找到项目根目录下的 core / ui 包。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_job_db(tmp_path, monkeypatch):
    """岗位测试不得写入真实 data/jobs.db。"""
    from core import job_db

    monkeypatch.setattr(job_db, "JOB_DB_PATH", tmp_path / "jobs.db")
