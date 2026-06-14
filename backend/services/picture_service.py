import logging
import fitz
from pathlib import Path
from backend.services.pdf_service import clip_region_as_image

logger = logging.getLogger(__name__)


def extract_picture(page: fitz.Page, bbox: tuple[float, float, float, float],
                    output_dir: str, element_id: int) -> dict:
    output_path = str(Path(output_dir) / f"picture_{element_id}.png")

    saved_path = clip_region_as_image(page, bbox, output_path)
    if not saved_path:
        return {"image_path": "", "format": "png"}

    return {
        "image_path": saved_path,
        "format": "png",
    }
