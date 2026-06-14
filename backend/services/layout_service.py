import os
import logging
import io
from pathlib import Path
from huggingface_hub import hf_hub_download
from ultralytics import YOLO
from PIL import Image, ImageDraw, ImageFont
from backend.config import MODELS_DIR, YOLO_MODEL_REPO, YOLO_MODEL_FILE, YOLO_IMG_SIZE, YOLO_DEVICE

logger = logging.getLogger(__name__)

_model = None

_raw_layout_data: dict[str, list[dict]] = {}


def set_raw_layout_data(image_path: str, raw_data: list[dict]):
    _raw_layout_data[image_path] = raw_data
    logger.info(f"Raw layout data saved for {Path(image_path).name}: {len(raw_data)} raw detections")


def get_raw_layout_data(image_path: str) -> list[dict]:
    return _raw_layout_data.get(image_path, [])


def clear_raw_layout_data(image_path: str):
    if image_path in _raw_layout_data:
        del _raw_layout_data[image_path]


def _string_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def deduplicate_header_footer(elements: list[dict], contents: dict[int, str], similarity_threshold: float = 0.8) -> list[dict]:
    header_footer_types = {"Page-header", "Page-footer"}
    
    header_footer_elems = [
        (idx, elem) for idx, elem in enumerate(elements)
        if elem["element_type"] in header_footer_types
    ]
    
    if len(header_footer_elems) < 2:
        return elements
    
    to_remove = set()
    
    for i in range(len(header_footer_elems)):
        idx1, elem1 = header_footer_elems[i]
        if idx1 in to_remove:
            continue
            
        for j in range(i + 1, len(header_footer_elems)):
            idx2, elem2 = header_footer_elems[j]
            if idx2 in to_remove:
                continue
            
            if elem1["element_type"] != elem2["element_type"]:
                continue
            
            iou = _compute_iou(elem1["bbox"], elem2["bbox"])
            if iou < 0.5:
                continue
            
            content1 = contents.get(idx1, "")
            content2 = contents.get(idx2, "")
            
            similarity = _string_similarity(content1, content2)
            if similarity < similarity_threshold:
                continue
            
            logger.info(f"Found overlapping {elem1['element_type']} (IoU={iou:.3f}, similarity={similarity:.3f})")
            
            if len(content1) >= len(content2):
                to_remove.add(idx2)
                logger.info(f"  Removing #{idx2} (len={len(content2)}), keeping #{idx1} (len={len(content1)})")
            else:
                to_remove.add(idx1)
                logger.info(f"  Removing #{idx1} (len={len(content1)}), keeping #{idx2} (len={len(content2)})")
                break
    
    if to_remove:
        elements = [elem for idx, elem in enumerate(elements) if idx not in to_remove]
        logger.info(f"Removed {len(to_remove)} duplicate header/footer elements")
    
    return elements


def _compute_iou(box_a: tuple, box_b: tuple) -> float:
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def _is_contained(box_a: tuple, box_b: tuple) -> bool:
    return (box_a[0] >= box_b[0] and
            box_a[1] >= box_b[1] and
            box_a[2] <= box_b[2] and
            box_a[3] <= box_b[3])


def _bbox_area(box: tuple) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def remove_overlapping_elements(elements: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    if len(elements) <= 1:
        return elements

    non_text_types = {t for t in YOLO_CATEGORY_MAP.values() if t != "Text"}

    def should_keep(elem, other):
        iou = _compute_iou(elem["bbox"], other["bbox"])

        elem_area = _bbox_area(elem["bbox"])
        other_area = _bbox_area(other["bbox"])

        if _is_contained(elem["bbox"], other["bbox"]):
            if elem_area < other_area:
                return False
            elif elem_area > other_area:
                return True
            else:
                if elem["element_type"] == "Text" and other["element_type"] != "Text":
                    return False
                elif elem["element_type"] != "Text" and other["element_type"] == "Text":
                    return True
                else:
                    return elem["confidence"] >= other["confidence"]

        if _is_contained(other["bbox"], elem["bbox"]):
            if other_area < elem_area:
                return True
            elif other_area > elem_area:
                return False
            else:
                if elem["element_type"] == "Text" and other["element_type"] != "Text":
                    return False
                elif elem["element_type"] != "Text" and other["element_type"] == "Text":
                    return True
                else:
                    return elem["confidence"] >= other["confidence"]

        if iou < iou_threshold:
            return True

        if elem["element_type"] == "Text" and other["element_type"] != "Text":
            return False
        elif elem["element_type"] != "Text" and other["element_type"] == "Text":
            return True
        else:
            return elem["confidence"] >= other["confidence"]

    kept = []
    for i, elem in enumerate(elements):
        keep = True
        for j, other in enumerate(elements):
            if i == j:
                continue
            if not should_keep(elem, other):
                keep = False
                break
        if keep:
            kept.append(elem)

    return kept

YOLO_CATEGORY_MAP = {
    0: "Caption",
    1: "Footnote",
    2: "Formula",
    3: "List-item",
    4: "Page-footer",
    5: "Page-header",
    6: "Picture",
    7: "Section-header",
    8: "Table",
    9: "Text",
    10: "Title",
}


def _get_model() -> YOLO:
    global _model
    if _model is not None:
        return _model

    model_path = MODELS_DIR / YOLO_MODEL_FILE
    if not model_path.exists():
        logger.info("Downloading YOLO26m model from HuggingFace Mirror...")
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        downloaded = hf_hub_download(
            repo_id=YOLO_MODEL_REPO,
            filename=YOLO_MODEL_FILE,
            repo_type="model",
            local_dir=str(MODELS_DIR),
        )
        model_path = Path(downloaded)

    logger.info(f"Loading YOLO26m model from {model_path}")
    
    import torch
    if YOLO_DEVICE == "cuda" and torch.cuda.is_available():
        try:
            _model = YOLO(str(model_path))
            _model.to("cuda")
            logger.info(f"YOLO model loaded on CUDA device: {torch.cuda.get_device_name(0)}")
        except Exception as e:
            logger.warning(f"Failed to load YOLO on CUDA: {e}, will use CPU")
            _model = YOLO(str(model_path))
    else:
        logger.info(f"YOLO model running on CPU")
        _model = YOLO(str(model_path))
    
    return _model


def _get_inference_kwargs() -> dict:
    import torch
    kwargs = {"imgsz": YOLO_IMG_SIZE, "verbose": False}
    if YOLO_DEVICE == "cuda" and torch.cuda.is_available():
        kwargs["device"] = "cuda"
        kwargs["half"] = True
    return kwargs


def detect_layout(image_path: str) -> list[dict]:
    model = _get_model()
    kwargs = _get_inference_kwargs()
    results = model(image_path, **kwargs)

    elements = []
    raw_elements = []
    if not results:
        set_raw_layout_data(image_path, [])
        return elements

    result = results[0]
    boxes = result.boxes
    if boxes is None:
        set_raw_layout_data(image_path, [])
        return elements

    for i in range(len(boxes)):
        box = boxes[i]
        xyxy = box.xyxy[0].cpu().numpy()
        conf = float(box.conf[0].cpu().numpy())
        cls_id = int(box.cls[0].cpu().numpy())

        element_type = YOLO_CATEGORY_MAP.get(cls_id, f"Unknown-{cls_id}")

        raw_elem = {
            "element_type": element_type,
            "bbox": (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
            "confidence": conf,
            "class_id": cls_id,
            "reading_order": -1,
        }
        raw_elements.append(raw_elem)

        elements.append({
            "element_type": element_type,
            "bbox": (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
            "confidence": conf,
            "reading_order": -1,
        })

    set_raw_layout_data(image_path, raw_elements)
    logger.info(f"Raw layout data for {Path(image_path).name}: {len(raw_elements)} raw detections before filtering")

    elements = remove_overlapping_elements(elements)
    return elements


def detect_layout_batch(image_paths: list[str]) -> list[list[dict]]:
    if not image_paths:
        return []

    model = _get_model()
    kwargs = _get_inference_kwargs()
    results = model(image_paths, **kwargs)

    all_elements = []
    for result_idx, result in enumerate(results):
        elements = []
        raw_elements = []
        image_path = image_paths[result_idx] if result_idx < len(image_paths) else ""
        
        boxes = result.boxes
        if boxes is not None:
            for i in range(len(boxes)):
                box = boxes[i]
                xyxy = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                cls_id = int(box.cls[0].cpu().numpy())
                element_type = YOLO_CATEGORY_MAP.get(cls_id, f"Unknown-{cls_id}")
                
                raw_elem = {
                    "element_type": element_type,
                    "bbox": (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                    "confidence": conf,
                    "class_id": cls_id,
                    "reading_order": -1,
                }
                raw_elements.append(raw_elem)
                
                elements.append({
                    "element_type": element_type,
                    "bbox": (float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                    "confidence": conf,
                    "reading_order": -1,
                })
        
        if image_path:
            set_raw_layout_data(image_path, raw_elements)
            logger.info(f"Raw layout data for {Path(image_path).name}: {len(raw_elements)} raw detections before filtering")
        
        elements = remove_overlapping_elements(elements)
        all_elements.append(elements)

    return all_elements


TYPE_COLORS = {
    "Caption": (255, 165, 0),
    "Footnote": (128, 128, 128),
    "Formula": (138, 43, 226),
    "List-item": (0, 128, 0),
    "Page-footer": (255, 0, 255),
    "Page-header": (255, 0, 255),
    "Picture": (255, 215, 0),
    "Section-header": (0, 0, 255),
    "Table": (255, 69, 0),
    "Text": (0, 191, 255),
    "Title": (220, 20, 60),
}


def generate_layout_annotation_image(image_path: str, raw_data: list[dict]) -> bytes:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except:
        try:
            font = ImageFont.truetype("simsun.ttc", 14)
        except:
            font = ImageFont.load_default()

    for idx, det in enumerate(raw_data):
        bbox = det["bbox"]
        element_type = det["element_type"]
        confidence = det["confidence"]
        color = TYPE_COLORS.get(element_type, (0, 255, 0))

        x0, y0, x1, y1 = bbox
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)

        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)

        label = f"#{idx} {element_type} {confidence:.2f}"
        bbox_text = draw.textbbox((0, 0), label, font=font)
        text_width = bbox_text[2] - bbox_text[0]
        text_height = bbox_text[3] - bbox_text[1]

        bg_x0 = x0
        bg_y0 = max(0, y0 - text_height - 4)
        bg_x1 = x0 + text_width + 8
        bg_y1 = y0

        draw.rectangle([bg_x0, bg_y0, bg_x1, bg_y1], fill=color)
        draw.text((x0 + 4, bg_y0 + 2), label, fill=(255, 255, 255), font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
