import os
import copy
import logging
import threading
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "llm_config.yaml"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "llm_config.yaml.example"

_lock = threading.Lock()
_cached_config: Optional[dict] = None


def _default_config() -> dict:
    return {
        "active_provider": "llamacpp",
        "providers": {
            "openai": {
                "configs": [
                    {
                        "name": "GPT-4o",
                        "api_key": "",
                        "model": "gpt-4o",
                        "base_url": "https://api.openai.com/v1",
                        "supports_vision": True,
                        "active": False,
                    }
                ]
            },
            "openrouter": {
                "configs": [
                    {
                        "name": "Default",
                        "api_key": "",
                        "model": "",
                        "base_url": "https://openrouter.ai/api/v1",
                        "supports_vision": False,
                        "active": False,
                    }
                ]
            },
            "claude": {
                "configs": [
                    {
                        "name": "Claude 3.5 Sonnet",
                        "api_key": "",
                        "model": "claude-3-5-sonnet-20241022",
                        "base_url": "https://api.anthropic.com",
                        "supports_vision": True,
                        "active": False,
                    }
                ]
            },
            "qwen": {
                "configs": [
                    {
                        "name": "Qwen-VL-Max",
                        "api_key": "",
                        "model": "qwen-vl-max",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "supports_vision": True,
                        "active": False,
                    }
                ]
            },
            "deepseek": {
                "configs": [
                    {
                        "name": "DeepSeek Chat",
                        "api_key": "",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com/v1",
                        "supports_vision": False,
                        "active": False,
                    }
                ]
            },
            "llamacpp": {
                "configs": [
                    {
                        "name": "PaddleOCR-VL",
                        "server_url": "http://127.0.0.1:8080",
                        "model_name": "PaddleOCR-VL-1.6.Q4_K_M.gguf",
                        "supports_vision": True,
                        "active": True,
                    }
                ]
            },
        },
    }


def load_config() -> dict:
    global _cached_config
    with _lock:
        if _cached_config is not None:
            return copy.deepcopy(_cached_config)

    config = None
    if CONFIG_PATH.exists():
        try:
            with open(str(CONFIG_PATH), "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            _validate_config(config)
        except Exception as e:
            logger.error(f"Failed to load llm_config.yaml: {e}, using default config")
            config = None

    if config is None:
        config = _default_config()

    with _lock:
        _cached_config = config

    return copy.deepcopy(config)


def save_config(config: dict):
    _validate_config(config)
    with open(str(CONFIG_PATH), "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    global _cached_config
    with _lock:
        _cached_config = copy.deepcopy(config)


def reload_config() -> dict:
    global _cached_config
    with _lock:
        _cached_config = None
    return load_config()


def get_active_config() -> Optional[dict]:
    config = load_config()
    active_provider = config.get("active_provider", "")
    providers = config.get("providers", {})

    if active_provider not in providers:
        return None

    provider = providers[active_provider]
    for cfg in provider.get("configs", []):
        if cfg.get("active"):
            result = copy.deepcopy(cfg)
            result["provider_type"] = active_provider
            return result

    return None


def set_active(provider_type: str, config_name: str) -> dict:
    config = load_config()
    providers = config.get("providers", {})

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}")

    target_found = False
    for provider_name, provider in providers.items():
        for cfg in provider.get("configs", []):
            if provider_name == provider_type and cfg.get("name") == config_name:
                cfg["active"] = True
                target_found = True
            else:
                cfg["active"] = False

    if not target_found:
        raise ValueError(f"Config '{config_name}' not found in provider '{provider_type}'")

    config["active_provider"] = provider_type
    save_config(config)
    return config


def update_provider_config(provider_type: str, config_name: str, updates: dict) -> dict:
    config = load_config()
    providers = config.get("providers", {})

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}")

    provider = providers[provider_type]
    target = None
    for cfg in provider.get("configs", []):
        if cfg.get("name") == config_name:
            target = cfg
            break

    if target is None:
        raise ValueError(f"Config '{config_name}' not found in provider '{provider_type}'")

    for key, value in updates.items():
        if key in ("name", "active"):
            continue
        target[key] = value

    save_config(config)
    return config


def add_provider_config(provider_type: str, new_config: dict) -> dict:
    config = load_config()
    providers = config.get("providers", {})

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}")

    provider = providers[provider_type]
    new_name = new_config.get("name", "")
    for cfg in provider.get("configs", []):
        if cfg.get("name") == new_name:
            raise ValueError(f"Config '{new_name}' already exists in provider '{provider_type}'")

    new_config["active"] = False
    provider["configs"].append(new_config)

    save_config(config)
    return config


def delete_provider_config(provider_type: str, config_name: str) -> dict:
    config = load_config()
    providers = config.get("providers", {})

    if provider_type not in providers:
        raise ValueError(f"Unknown provider: {provider_type}")

    provider = providers[provider_type]
    was_active = False
    new_configs = []
    for cfg in provider.get("configs", []):
        if cfg.get("name") == config_name:
            was_active = cfg.get("active", False)
            continue
        new_configs.append(cfg)

    if len(new_configs) == len(provider["configs"]):
        raise ValueError(f"Config '{config_name}' not found in provider '{provider_type}'")

    provider["configs"] = new_configs

    if was_active and new_configs:
        new_configs[0]["active"] = True

    save_config(config)
    return config


PROVIDER_TYPES = {"openai", "openrouter", "claude", "qwen", "deepseek", "llamacpp"}

API_PROVIDER_FIELDS = {
    "openai": {"api_key", "model", "base_url", "supports_vision"},
    "openrouter": {"api_key", "model", "base_url", "supports_vision"},
    "claude": {"api_key", "model", "base_url", "supports_vision"},
    "qwen": {"api_key", "model", "base_url", "supports_vision"},
    "deepseek": {"api_key", "model", "base_url", "supports_vision"},
    "llamacpp": {"server_url", "model_name", "supports_vision"},
}


def _validate_config(config: dict):
    if not isinstance(config, dict):
        raise ValueError("Config must be a dictionary")

    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("'providers' must be a dictionary")

    for provider_name, provider in providers.items():
        if provider_name not in PROVIDER_TYPES:
            raise ValueError(f"Unknown provider type: {provider_name}")

        if not isinstance(provider, dict):
            raise ValueError(f"Provider '{provider_name}' must be a dictionary")

        configs = provider.get("configs", [])
        if not isinstance(configs, list):
            raise ValueError(f"Provider '{provider_name}' configs must be a list")

        active_count = 0
        for cfg in configs:
            if not isinstance(cfg, dict):
                raise ValueError(f"Config entry must be a dictionary in provider '{provider_name}'")
            if "name" not in cfg:
                raise ValueError(f"Each config must have a 'name' in provider '{provider_name}'")
            if "supports_vision" not in cfg:
                raise ValueError(f"Each config must have 'supports_vision' in provider '{provider_name}'")
            if cfg.get("active"):
                active_count += 1

        if active_count > 1:
            raise ValueError(f"Provider '{provider_name}' can only have one active config, found {active_count}")
