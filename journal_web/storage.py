from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import current_app

JOURNAL_MODE_EDITING = 'editing'
JOURNAL_MODE_COMPLETE = 'complete'
JOURNAL_MODES = {JOURNAL_MODE_EDITING, JOURNAL_MODE_COMPLETE}


def normalize_journal_mode(meta: dict[str, Any]) -> str:
    mode = (meta.get('mode') or JOURNAL_MODE_EDITING).strip().lower()
    return mode if mode in JOURNAL_MODES else JOURNAL_MODE_EDITING

# TRUNCATED TEST
