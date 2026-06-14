import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

TMP_DIR = BASE_DIR / "tmp"
MODELS_DIR = BASE_DIR / "models"
DB_PATH = BASE_DIR / "data.db"

TMP_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

HF_MIRROR_URL = "https://hf-mirror.com"
YOLO_MODEL_REPO = "Armaggheddon/yolo26-document-layout"
YOLO_MODEL_FILE = "yolo26m_doc_layout.pt"
YOLO_IMG_SIZE = 1280
YOLO_DEVICE = "cpu"

SURYA_ORDER_MODEL_REPO = "vikp/surya_order"

SCAN_TEXT_THRESHOLD = 10
SCAN_IMAGE_AREA_RATIO = 0.8

GARBLE_CJK_THRESHOLD = 0.3

TABLE_STRATEGY = "lines_strict"
