"""Chunker — tách tài liệu thành đoạn trước khi embed.

Strategy pattern: mọi chunker cùng tuân Chunker Protocol, đổi được để A/B test
ảnh hưởng của chunking lên điểm eval mà không sửa pipeline.
"""

from __future__ import annotations

import re

from src.data.contracts import Chunk, Chunker, LoadedDocument  # noqa: F401

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


# Lùi tối đa ngần này ký tự để tìm khoảng trắng khi cắt chunk. Xa hơn thì
# chunk ngắn đi đáng kể mà chẳng lợi gì.
_LUI_TOI_DA = 80


class ParagraphChunker:
    """Tách theo đoạn, gộp lại cho đủ kích thước mục tiêu.

    Tôn trọng ranh giới đoạn nên không cắt vỡ bảng biểu giữa chừng.
    """

    def __init__(self, target_chars: int = 900, overlap_chars: int = 120) -> None:
        if overlap_chars >= target_chars:
            raise ValueError("overlap_chars phải nhỏ hơn target_chars")
        self._target = target_chars
        self._overlap = overlap_chars

    def split(self, document: LoadedDocument) -> list[Chunk]:
        paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(document.text) if p.strip()]
        if not paragraphs:
            return []

        pieces: list[str] = []
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if len(candidate) <= self._target:
                buffer = candidate
                continue

            tail = self._duoi_chong_lan(buffer)
            if buffer:
                pieces.append(buffer)

            # Đoạn mới (kể cả cộng thêm tail overlap) có thể vẫn vượt target —
            # phải cắt cứng ngay, không được gán thẳng làm buffer mới, nếu
            # không chunk cuối cùng sẽ phình to hơn target nhiều lần.
            merged = f"{tail}\n\n{paragraph}" if tail else paragraph
            if len(merged) <= self._target:
                buffer = merged
            else:
                *full_pieces, buffer = self._hard_split(merged)
                pieces.extend(full_pieces)
        if buffer:
            pieces.append(buffer)

        return [
            Chunk(
                id=f"{document.doc_id}::{index}",
                text=piece,
                doc_id=document.doc_id,
                doc_title=document.title,
                version=str(document.metadata.get("version", "")),
                section=str(document.metadata.get("section", "")),
                visibility=document.metadata.get("visibility", "public"),
                metadata=document.metadata,
            )
            for index, piece in enumerate(pieces)
        ]

    def _duoi_chong_lan(self, text: str) -> str:
        """Phần đuôi mang sang chunk sau, nắn về ĐẦU TỪ gần nhất.

        Cắt thẳng `text[-overlap:]` thì gần như chunk nào cũng mở đầu bằng chữ
        cụt ("ãi suất…" thay vì "lãi suất…"). Đây là đường đi chính — gộp theo
        đoạn — nên lỗi này phổ biến hơn hẳn lỗi cùng loại ở `_hard_split`.
        """
        if not text or not self._overlap:
            return ""
        duoi = text[-self._overlap :]
        khoang_trang = duoi.find(" ")
        return duoi[khoang_trang + 1 :] if khoang_trang >= 0 else duoi

    def _hard_split(self, text: str) -> list[str]:
        """Đoạn dài hơn target thì cắt, nhưng LÙI VỀ ranh giới từ gần nhất.

        Cắt đúng theo số ký tự sẽ chặt giữa từ: có chunk trong kho bắt đầu bằng
        "ặt bằng, cam kết…". Token đầu thành rác, và embedding của cả chunk kém
        theo. Lùi tối đa `_LUI_TOI_DA` ký tự để tìm khoảng trắng; không thấy thì
        đành cắt cứng, còn hơn sinh chunk dài vô hạn.
        """
        mieng: list[str] = []

        dau = 0
        while dau < len(text):
            cuoi = min(dau + self._target, len(text))
            if cuoi < len(text):
                cat = text.rfind(" ", cuoi - _LUI_TOI_DA, cuoi)
                if cat > dau:
                    cuoi = cat
            mieng.append(text[dau:cuoi].strip())
            if cuoi >= len(text):
                break

            # Bước kế tiếp tính từ điểm cắt THẬT, không phải bội số cố định —
            # nếu không, phần chồng lấn trôi dần và có đoạn bị bỏ sót.
            ke_tiep = max(dau + 1, cuoi - self._overlap)
            # Điểm BẮT ĐẦU cũng phải là ranh giới từ. Chỉ nắn điểm cắt cuối thì
            # phần chồng lấn vẫn mở đầu bằng chữ cụt — đúng lỗi đang sửa.
            khoang_trang = text.find(" ", ke_tiep)
            if 0 <= khoang_trang < cuoi:
                ke_tiep = khoang_trang + 1
            dau = ke_tiep

        return [m for m in mieng if m]
