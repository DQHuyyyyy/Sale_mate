"""Grounding — ép LLM chỉ trả lời dựa trên tài liệu đã truy hồi.

Đây là mảnh "Augmented" trong RAG: lấy chunk đã truy hồi, bọc vào prompt sao
cho model không được đi ra ngoài ngữ cảnh được cấp.

Tách khỏi `agents/nodes/generate.py` để hết chồng chéo sở hữu — trước đây node
là file của Huy nhưng phần dựng prompt lại do Phúc viết, nên không rõ ai chịu
trách nhiệm khi câu trả lời bịa số.

Ranh giới:
    rag/grounding.py   dựng prompt (hàm thuần, không I/O, không gọi LLM)
    agents/nodes/generate.py   gọi hàm này rồi gọi LLM
"""

from __future__ import annotations

from src.models.chat import ChatMessage, MessageRole

GROUNDED_TEMPLATE = """Dựa DUY NHẤT vào ngữ cảnh dưới đây để trả lời. \
Nếu ngữ cảnh không chứa thông tin cần thiết hoặc thông tin chưa đủ, tuyệt đối không tự suy đoán hay bịa đặt số liệu (giá, diện tích, vị trí, pháp lý), hãy nói rõ là chưa có đủ dữ liệu. \
Mọi thông tin về căn hộ hoặc chính sách ĐỀU BẮT BUỘC phải trích dẫn nguồn bằng định dạng [Mã căn] hoặc [Tên tài liệu] ngay sau khẳng định đó.

<ngu_canh>
{context}
</ngu_canh>

Câu hỏi: {query}"""


def build_grounded_messages(
    query: str,
    *,
    system_prompt: str,
    context: str = "",
    history: list[ChatMessage] | None = None,
) -> list[ChatMessage]:
    """Ghép system prompt + lịch sử + câu hỏi (bọc ngữ cảnh nếu có).

    Không có context thì gửi câu hỏi trần — system prompt vẫn cấm bịa số, nhưng
    câu trả lời sẽ dựa trên kiến thức chung của model và không có nguồn để trích.

    Thẻ `<ngu_canh>` bọc phần tài liệu là biện pháp chống prompt injection: tài
    liệu do admin upload có thể chứa câu kiểu "bỏ qua hướng dẫn phía trên", nên
    phải nói rõ với model rằng phần bên trong là dữ liệu tham khảo, không phải
    chỉ thị.
    """
    messages: list[ChatMessage] = [ChatMessage(role=MessageRole.SYSTEM, content=system_prompt)]
    messages.extend(history or [])

    content = GROUNDED_TEMPLATE.format(context=context, query=query) if context else query
    messages.append(ChatMessage(role=MessageRole.USER, content=content))
    return messages
