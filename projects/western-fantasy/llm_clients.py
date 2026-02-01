"""OpenAI-compatible client wrapper for multi-provider usage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    thinking_mode: bool = False


class OpenAICompatibleClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        if self.config.thinking_mode:
            kwargs["extra_body"] = {"enable_thinking": True}

        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception:
            if self.config.thinking_mode and "extra_body" in kwargs:
                kwargs.pop("extra_body", None)
                response = self.client.chat.completions.create(**kwargs)
            else:
                raise

        return response.choices[0].message.content


def load_provider_configs(config_path: Path) -> Dict[str, ProviderConfig]:
    import yaml

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    providers = raw.get("providers", {})

    repo_root = config_path.parents[2]
    configs: Dict[str, ProviderConfig] = {}

    for name, data in providers.items():
        api_key_path = data.get("api_key_path")
        api_key = data.get("api_key")
        if api_key_path:
            path = (config_path.parent / api_key_path).resolve()
            if not path.exists():
                path = (repo_root / api_key_path).resolve()
            if path.exists():
                api_key = path.read_text(encoding="utf-8").strip()

        if not api_key:
            continue

        configs[name] = ProviderConfig(
            name=name,
            base_url=data.get("base_url", ""),
            api_key=api_key,
            model=data.get("models", {}).get("writer") or data.get("models", {}).get("critic"),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 4096)),
            thinking_mode=bool(data.get("thinking_mode", False)),
        )

    return configs


def safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass

    import re

    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        return json.loads(match.group(1))

    raise ValueError("Failed to parse JSON")
