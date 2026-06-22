import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_parse_progress: dict[int, dict] = {}


def set_parse_progress(doc_id: int, stage: str, percent: float, message: str = ""):
    _parse_progress[doc_id] = {
        "stage": stage,
        "percent": round(percent, 1),
        "message": message,
        "updated_at": _get_progress_time()
    }
    logger.info(f"Parse progress for doc {doc_id}: {percent:.1f}% - {stage} - {message}")


def get_parse_progress(doc_id: int) -> dict:
    return _parse_progress.get(doc_id, {"stage": "idle", "percent": 0, "message": ""})


def clear_parse_progress(doc_id: int):
    if doc_id in _parse_progress:
        del _parse_progress[doc_id]


def _get_progress_time() -> str:
    return datetime.now().isoformat()
