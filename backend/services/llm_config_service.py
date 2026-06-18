import json
import uuid
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = BASE_DIR / "llm_config_local.json"

MODEL_TYPES = {
    "openai": {
        "name": "OpenAI",
        "icon": "fa-robot",
        "fields": ["api_key", "base_url", "model", "temperature", "max_tokens"],
        "defaults": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "supports_vision": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "icon": "fa-network-wired",
        "fields": ["api_key", "base_url", "model", "temperature", "max_tokens"],
        "defaults": {
            "base_url": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-4o",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "supports_vision": True,
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "icon": "fa-brain",
        "fields": ["api_key", "base_url", "model", "temperature", "max_tokens"],
        "defaults": {
            "base_url": "https://api.anthropic.com",
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "supports_vision": True,
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "icon": "fa-cloud",
        "fields": ["api_key", "base_url", "model", "temperature", "max_tokens"],
        "defaults": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "supports_vision": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "icon": "fa-gem",
        "fields": ["api_key", "base_url", "model", "temperature", "max_tokens"],
        "defaults": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 4096,
        },
        "supports_vision": False,
    },
    "llamacpp": {
        "name": "本地 LlamaCPP",
        "icon": "fa-server",
        "fields": ["base_url", "model", "temperature", "max_tokens", "api_key"],
        "defaults": {
            "base_url": "http://localhost:8080/v1",
            "model": "local-model",
            "temperature": 0.7,
            "max_tokens": 4096,
            "api_key": "sk-no-key-required",
        },
        "supports_vision": False,
    },
}


@dataclass
class LLMConfig:
    id: str
    type: str
    name: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    supports_vision: bool = False
    is_active: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


def _default_configs() -> dict:
    configs = {}
    for type_key in MODEL_TYPES:
        configs[type_key] = []
    return configs


def _ensure_config_file():
    if not CONFIG_FILE.exists():
        default_data = {
            "configs": _default_configs(),
            "active_type": "openai",
        }
        _save_config_file(default_data)
    else:
        try:
            data = _load_config_file()
            if "configs" not in data:
                data["configs"] = _default_configs()
            for type_key in MODEL_TYPES:
                if type_key not in data["configs"]:
                    data["configs"][type_key] = []
            if "active_type" not in data:
                data["active_type"] = "openai"
            _save_config_file(data)
        except Exception as e:
            logger.error(f"Error ensuring config file: {e}")
            default_data = {
                "configs": _default_configs(),
                "active_type": "openai",
            }
            _save_config_file(default_data)


def _load_config_file() -> dict:
    if not CONFIG_FILE.exists():
        _ensure_config_file()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config_file(data: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_model_types() -> dict:
    return MODEL_TYPES


def get_all_configs() -> dict:
    _ensure_config_file()
    data = _load_config_file()
    return {
        "model_types": MODEL_TYPES,
        "active_type": data.get("active_type", "openai"),
        "configs": data.get("configs", _default_configs()),
    }


def get_configs_by_type(type_key: str) -> list:
    _ensure_config_file()
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")
    data = _load_config_file()
    return data.get("configs", {}).get(type_key, [])


def get_active_config() -> Optional[dict]:
    _ensure_config_file()
    data = _load_config_file()
    active_type = data.get("active_type", "openai")
    configs = data.get("configs", {}).get(active_type, [])
    for cfg in configs:
        if cfg.get("is_active"):
            return cfg
    return None


def get_active_type() -> str:
    _ensure_config_file()
    data = _load_config_file()
    return data.get("active_type", "openai")


def set_active_type(type_key: str) -> bool:
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")
    _ensure_config_file()
    data = _load_config_file()
    data["active_type"] = type_key
    _save_config_file(data)
    return True


def create_config(type_key: str, config_data: dict) -> dict:
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")

    type_info = MODEL_TYPES[type_key]
    defaults = type_info["defaults"]
    now = datetime.now().isoformat()

    new_cfg = {
        "id": str(uuid.uuid4()),
        "type": type_key,
        "name": config_data.get("name", f"{type_info['name']} 配置"),
        "api_key": config_data.get("api_key", defaults.get("api_key", "")),
        "base_url": config_data.get("base_url", defaults.get("base_url", "")),
        "model": config_data.get("model", defaults.get("model", "")),
        "temperature": float(config_data.get("temperature", defaults.get("temperature", 0.7))),
        "max_tokens": int(config_data.get("max_tokens", defaults.get("max_tokens", 4096))),
        "supports_vision": bool(config_data.get("supports_vision", type_info["supports_vision"])),
        "is_active": False,
        "created_at": now,
        "updated_at": now,
    }

    _ensure_config_file()
    data = _load_config_file()
    if type_key not in data["configs"]:
        data["configs"][type_key] = []
    data["configs"][type_key].append(new_cfg)
    _save_config_file(data)
    return new_cfg


def update_config(type_key: str, config_id: str, config_data: dict) -> Optional[dict]:
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")

    _ensure_config_file()
    data = _load_config_file()
    configs = data.get("configs", {}).get(type_key, [])

    for i, cfg in enumerate(configs):
        if cfg["id"] == config_id:
            now = datetime.now().isoformat()
            for key in ["name", "api_key", "base_url", "model", "supports_vision"]:
                if key in config_data:
                    cfg[key] = config_data[key]
            if "temperature" in config_data:
                cfg["temperature"] = float(config_data["temperature"])
            if "max_tokens" in config_data:
                cfg["max_tokens"] = int(config_data["max_tokens"])
            cfg["updated_at"] = now
            configs[i] = cfg
            _save_config_file(data)
            return cfg
    return None


def delete_config(type_key: str, config_id: str) -> bool:
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")

    _ensure_config_file()
    data = _load_config_file()
    configs = data.get("configs", {}).get(type_key, [])

    for i, cfg in enumerate(configs):
        if cfg["id"] == config_id:
            del configs[i]
            data["configs"][type_key] = configs
            _save_config_file(data)
            return True
    return False


def set_active_config(type_key: str, config_id: str) -> bool:
    if type_key not in MODEL_TYPES:
        raise ValueError(f"Unknown model type: {type_key}")

    _ensure_config_file()
    data = _load_config_file()
    configs = data.get("configs", {}).get(type_key, [])

    found = False
    for i, cfg in enumerate(configs):
        if cfg["id"] == config_id:
            cfg["is_active"] = True
            found = True
        else:
            cfg["is_active"] = False

    if not found:
        return False

    data["active_type"] = type_key
    _save_config_file(data)
    return True


_ensure_config_file()
