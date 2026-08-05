"""Embedder — sinh vector cho văn bản.

Hai cài đặt:
- OpenAIEmbedder: mặc định hiện tại (đã có OPENAI_API_KEY).
- FakeEmbedder: xác định (deterministic), không gọi mạng — dùng cho test/dev.

BGE-M3 (mạnh tiếng Việt) sẽ là cài đặt thứ ba, thêm sau khi bật requirements-ml.txt.
Vì cả ba cùng tuân Embedder Protocol nên đổi chỉ sửa src/bootstrap.py.
"""

from __future__ import annotations

import hashlib
import math

from openai import AsyncOpenAI

from src.core.exceptions import UpstreamError
from src.data.contracts import Embedder  # noqa: F401 - tài liệu hoá hợp đồng


class OpenAIEmbedder:
    """Gọi API embedding của OpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._dimension = dimension
        self._client = client or AsyncOpenAI(api_key=api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.embeddings.create(model=self._model, input=texts)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError("Gọi API embedding thất bại.") from exc
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0] if vectors else []


class FakeEmbedder:
    """Embedder giả lập, không gọi mạng.

    Sinh vector từ hash của từng token nên cùng một text luôn ra cùng vector,
    và hai text chia sẻ nhiều từ sẽ gần nhau — đủ để test luồng truy hồi.
    """

    def __init__(self, dimension: int = 64) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text)

    def _vectorize(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]
