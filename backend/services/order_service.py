import logging
import os
from PIL import Image
from backend.services.layout_service import detect_layout
from backend.config import MODELS_DIR, HF_MIRROR_URL, SURYA_ORDER_MODEL_REPO

logger = logging.getLogger(__name__)

_order_model = None
_order_processor = None


def _download_surya_order_model() -> str:
    local_dir = MODELS_DIR / "surya_order"
    local_dir.mkdir(parents=True, exist_ok=True)

    marker_file = local_dir / "config.json"
    if marker_file.exists():
        logger.info(f"Surya order model already downloaded at {local_dir}")
        return str(local_dir)

    logger.info(f"Downloading {SURYA_ORDER_MODEL_REPO} from {HF_MIRROR_URL} to {local_dir}...")

    os.environ["HF_ENDPOINT"] = HF_MIRROR_URL

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except:
        pass

    try:
        from huggingface_hub import snapshot_download
        import ssl
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context

        snapshot_download(
            repo_id=SURYA_ORDER_MODEL_REPO,
            local_dir=str(local_dir),
        )
        logger.info(f"Surya order model downloaded successfully to {local_dir}")
    except Exception as e:
        logger.warning(f"Failed to download Surya order model: {e}")
        import traceback
        logger.warning(traceback.format_exc())

    return str(local_dir)


def _get_ordering_model_and_processor():
    global _order_model, _order_processor
    if _order_model is not None and _order_processor is not None:
        return _order_model, _order_processor

    try:
        import os
        os.environ["HF_ENDPOINT"] = HF_MIRROR_URL

        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except:
            pass
        import ssl
        try:
            _create_unverified_https_context = ssl._create_unverified_context
        except AttributeError:
            pass
        else:
            ssl._create_default_https_context = _create_unverified_https_context

        local_model_path = _download_surya_order_model()

        from surya.model.ordering.model import load_model as order_load_model
        from surya.model.ordering.processor import load_processor as order_load_processor

        logger.info(f"Loading Surya ordering model from {local_model_path} on CPU...")
        _order_model = order_load_model(checkpoint=local_model_path, device="cpu")
        _order_processor = order_load_processor(checkpoint=local_model_path)
        logger.info("Surya ordering model loaded successfully on CPU")
    except Exception as e:
        logger.warning(f"Failed to load Surya ordering model: {e}. Will use fallback reading order.")
        import traceback
        logger.warning(traceback.format_exc())
        _order_model = None
        _order_processor = None

    return _order_model, _order_processor


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


def _fallback_reading_order(elements: list[dict]) -> list[dict]:
    sorted_elements = sorted(elements, key=lambda e: (e["bbox"][1], e["bbox"][0]))
    for i, elem in enumerate(sorted_elements):
        elem["reading_order"] = i
    return sorted_elements


def assign_reading_order(elements: list[dict], image_path: str) -> list[dict]:
    if not elements:
        return elements

    model, processor = _get_ordering_model_and_processor()

    if model is None or processor is None:
        logger.info("Using fallback reading order (top-to-bottom, left-to-right)")
        return _fallback_reading_order(elements)

    try:
        from surya.ordering import batch_ordering
        import math

        image = Image.open(image_path)
        image_size = image.size

        bboxes = []
        for elem in elements:
            bbox = elem["bbox"]
            x0, y0, x1, y1 = bbox
            x0 = max(0, math.floor(x0))
            y0 = max(0, math.floor(y0))
            x1 = min(image_size[0], math.ceil(x1))
            y1 = min(image_size[1], math.ceil(y1))
            bboxes.append([x0, y0, x1, y1])

        ordering_results = batch_ordering([image], [bboxes], model, processor)

        if not ordering_results or not ordering_results[0].bboxes:
            logger.warning("Surya batch_ordering returned no results, using fallback")
            return _fallback_reading_order(elements)

        surya_boxes = []
        for bbox_info in ordering_results[0].bboxes:
            if hasattr(bbox_info, 'bbox'):
                bbox = tuple(bbox_info.bbox)
            elif hasattr(bbox_info, 'polygon'):
                poly = bbox_info.polygon
                bbox = (poly[0][0], poly[0][1], poly[2][0], poly[2][1])
            else:
                bbox = (0, 0, 0, 0)

            position = bbox_info.position if hasattr(bbox_info, 'position') else 0
            surya_boxes.append({"bbox": bbox, "position": position})

        surya_boxes.sort(key=lambda s: s["position"])

        for elem in elements:
            best_iou = 0.0
            best_position = len(elements)

            elem_bbox = elem["bbox"]

            for sbox in surya_boxes:
                iou = _compute_iou(elem_bbox, sbox["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_position = sbox["position"]

            elem["reading_order"] = best_position

        elements.sort(key=lambda e: e["reading_order"])
        for i, elem in enumerate(elements):
            elem["reading_order"] = i

        return elements

    except Exception as e:
        logger.error(f"Surya batch_ordering failed: {e}, using fallback")
        import traceback
        logger.error(traceback.format_exc())
        return _fallback_reading_order(elements)


def assign_reading_order_batch(pages_elements: list[list[dict]], image_paths: list[str]) -> list[list[dict]]:
    model, processor = _get_ordering_model_and_processor()

    if model is None or processor is None:
        logger.info("Using fallback reading order for all pages")
        return [_fallback_reading_order(elems) for elems in pages_elements]

    try:
        from surya.ordering import batch_ordering
        import math

        all_images = []
        all_bboxes = []
        valid_indices = []
        image_sizes = []

        for idx, (elements, image_path) in enumerate(zip(pages_elements, image_paths)):
            if not elements:
                continue

            image = Image.open(image_path)
            image_size = image.size
            all_images.append(image)
            image_sizes.append(image_size)

            page_bboxes = []
            for elem in elements:
                bbox = elem["bbox"]
                x0, y0, x1, y1 = bbox
                x0 = max(0, math.floor(x0))
                y0 = max(0, math.floor(y0))
                x1 = min(image_size[0], math.ceil(x1))
                y1 = min(image_size[1], math.ceil(y1))
                page_bboxes.append([x0, y0, x1, y1])
            all_bboxes.append(page_bboxes)
            valid_indices.append(idx)

        if not all_images:
            return [_fallback_reading_order(elems) for elems in pages_elements]

        ordering_results = batch_ordering(all_images, all_bboxes, model, processor)

        result = [_fallback_reading_order(elems) for elems in pages_elements]

        for res_idx, page_idx in enumerate(valid_indices):
            if res_idx >= len(ordering_results) or not ordering_results[res_idx].bboxes:
                continue

            elements = pages_elements[page_idx]

            surya_boxes = []
            for bbox_info in ordering_results[res_idx].bboxes:
                if hasattr(bbox_info, 'bbox'):
                    bbox = tuple(bbox_info.bbox)
                elif hasattr(bbox_info, 'polygon'):
                    poly = bbox_info.polygon
                    bbox = (poly[0][0], poly[0][1], poly[2][0], poly[2][1])
                else:
                    bbox = (0, 0, 0, 0)
                position = bbox_info.position if hasattr(bbox_info, 'position') else 0
                surya_boxes.append({"bbox": bbox, "position": position})

            surya_boxes.sort(key=lambda s: s["position"])

            for elem in elements:
                best_iou = 0.0
                best_position = len(elements)
                elem_bbox = elem["bbox"]

                for sbox in surya_boxes:
                    iou = _compute_iou(elem_bbox, sbox["bbox"])
                    if iou > best_iou:
                        best_iou = iou
                        best_position = sbox["position"]

                elem["reading_order"] = best_position

            elements.sort(key=lambda e: e["reading_order"])
            for i, elem in enumerate(elements):
                elem["reading_order"] = i

            result[page_idx] = elements

        return result

    except Exception as e:
        logger.error(f"Surya batch_ordering failed: {e}, using fallback")
        import traceback
        logger.error(traceback.format_exc())
        return [_fallback_reading_order(elems) for elems in pages_elements]
