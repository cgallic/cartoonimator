"""GPT Image 2 client via OpenRouter — used by library generation only.

Daily render path does not call this; library is a one-time setup.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass

import requests


class GPTImageError(RuntimeError):
    pass


@dataclass
class GeneratedImage:
    png_bytes: bytes


_DEFAULT_MODEL = "openai/gpt-5.4-image-2"
_DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"


class GPTImageClient:
    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        endpoint: str = _DEFAULT_URL,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        n: int = 1,
        anchor_image: bytes | None = None,
        thinking: bool = False,
    ) -> list[GeneratedImage]:
        content: list[dict] = []
        if anchor_image is not None:
            anchor_b64 = base64.b64encode(anchor_image).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{anchor_b64}"},
            })
        content.append({"type": "text", "text": prompt})

        body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "n": n,
        }
        if thinking:
            body["reasoning"] = {"effort": "high"}

        resp = requests.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise GPTImageError(
                f"GPT Image 2 returned {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        images = message.get("images", [])
        if not images:
            raise GPTImageError(f"No images in response: {data}")

        out: list[GeneratedImage] = []
        for img in images:
            url = img.get("image_url", {}).get("url", "")
            if not url.startswith("data:image/"):
                raise GPTImageError(f"Unexpected image url shape: {url[:80]}")
            _, b64 = url.split(",", 1)
            out.append(GeneratedImage(png_bytes=base64.b64decode(b64)))
        return out
