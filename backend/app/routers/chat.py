from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import ChatError, generate_reply

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    _: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """CONTRACT CỐ ĐỊNH: {message, history} -> {reply}.

    Giai đoạn 7 thay lõi trong app/services/chat.py; router này không đổi, nên
    frontend cũng không phải sửa.
    """
    try:
        reply = await generate_reply(payload.message, payload.history)
    except ChatError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return ChatResponse(reply=reply)
