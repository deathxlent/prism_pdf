import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from backend.database import init_db
from backend.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

logger = logging.getLogger(__name__)


def _check_model_configs():
    from backend.services.llm_config_service import get_all_configs, get_active_config, get_active_type
    try:
        all_data = get_all_configs()
        configs = all_data.get("configs", {})
        active_type = get_active_type()
        active_config = get_active_config()

        has_active_llm = active_config is not None and active_type != "paddlevl"
        has_active_paddlevl = False
        for cfg in configs.get("paddlevl", []):
            if cfg.get("is_active"):
                has_active_paddlevl = True
                break

        has_any_llm_config = False
        for tk, cfgs in configs.items():
            if tk != "paddlevl" and len(cfgs) > 0:
                has_any_llm_config = True
                break

        has_any_paddlevl_config = len(configs.get("paddlevl", [])) > 0

        print("")
        print("=" * 60)
        print("  Model Configuration Status")
        print("=" * 60)

        if has_active_llm:
            cfg_name = active_config.get("name", "Unknown")
            logger.info(f"  [OK] LLM Translation: {active_type} - {cfg_name}")
        else:
            if has_any_llm_config:
                logger.warning("  [!!] LLM config exists but none is active. Please activate one.")
            else:
                logger.warning("  [!!] No LLM translation model configured.")
            print("")
            print("  LLM (translation) model is NOT configured or not active.")
            print("  Impact: PDF text translation will NOT work.")
            print("  Fix: Open http://localhost:8000 -> Settings -> LLM Config")
            print("       Add an API-based model (e.g., OpenAI, DeepSeek) or")
            print("       start a local LlamaCPP server and add its URL.")

        if has_active_paddlevl:
            pvl_cfg = None
            for cfg in configs.get("paddlevl", []):
                if cfg.get("is_active"):
                    pvl_cfg = cfg
                    break
            logger.info(f"  [OK] PaddleVL OCR: {pvl_cfg.get('name', 'Unknown')}")
        else:
            if has_any_paddlevl_config:
                logger.warning("  [!!] PaddleVL config exists but none is active. Please activate one.")
            else:
                logger.warning("  [!!] No PaddleVL OCR model configured.")
            print("")
            print("  PaddleVL (OCR) model is NOT configured or not active.")
            print("  Impact: Scanned PDF image text extraction will NOT work.")
            print("  Fix: Start PaddleOCR-VL via llama.cpp (port 8080), then")
            print("       Open http://localhost:8000 -> Settings -> LLM Config -> PaddleVL")
            print("       Add the PaddleVL service URL (e.g., http://localhost:8080/v1).")

        print("")
        print("  NOTE: Insufficient VRAM may cause model loading failures or")
        print("  slow inference. PaddleOCR-VL requires ~1.2GB VRAM (Q4).")
        print("  If VRAM is insufficient, the OCR service may crash or fall")
        print("  back to CPU mode, which will be significantly slower.")
        print("")
        print("=" * 60)
        print("")
    except Exception as e:
        logger.warning(f"Failed to check model configs: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    _check_model_configs()
    yield


app = FastAPI(title="Prism PDF - High Precision PDF Parser", version="1.0.0", lifespan=lifespan)

app.include_router(router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/api/file/{file_path:path}")
async def serve_file(file_path: str):
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}, 404


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
