"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ArrowRightIcon,
  ChatBubbleIcon,
  CloseIcon,
  RefreshIcon,
  SendIcon,
  SparkleIcon,
  SparkleSmallIcon,
} from "@/components/ui/icons";
import { streamChat } from "@/lib/chat";
import type { ChatMessage } from "@/lib/types";

const MAX_CHARS = 2000;

const QUICK_ACTIONS = [
  "Tư vấn giá theo khu vực",
  "Tìm căn hộ phù hợp",
  "Đặt câu hỏi pháp lý",
  "Viết tin đăng",
];

/** Gợi ý hỏi tiếp sau mỗi câu trả lời — dẫn dắt người dùng đi tiếp. */
const FOLLOW_UPS: Record<string, string[]> = {
  "Tư vấn giá theo khu vực": [
    "Giá khu vực Cầu Giấy, Hà Nội?",
    "Nên mua chung cư hay nhà trong ngõ?",
  ],
  "Tìm căn hộ phù hợp": [
    "Căn 2PN dưới 4 tỷ ở Hà Nội",
    "So sánh 2 dự án ven hồ",
  ],
  "Đặt câu hỏi pháp lý": [
    "Thủ tục sang tên sổ đỏ gồm những gì?",
    "Thuế phí khi mua căn hộ?",
  ],
  "Viết tin đăng": [
    "Viết tin bán căn hộ 2PN 68m²",
    "Tối ưu tiêu đề cho tin đăng",
  ],
};

const DEFAULT_FOLLOW_UPS = ["Tư vấn giá theo khu vực", "Viết tin đăng"];

interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  followUps?: string[];
}

export function AIWidget() {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string>();

  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController>(null);

  // Luôn cuộn xuống tin mới nhất.
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [turns]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Esc để đóng panel — chuẩn cho dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Rời trang thì huỷ stream đang chạy.
  useEffect(() => () => abortRef.current?.abort(), []);

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || busy) return;

      const history: ChatMessage[] = turns.map((turn) => ({
        role: turn.role,
        content: turn.content,
      }));

      const answerId = crypto.randomUUID();
      setTurns((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: text },
        { id: answerId, role: "assistant", content: "" },
      ]);
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const event of streamChat({
          message: text,
          sessionId,
          history,
          signal: controller.signal,
        })) {
          if (event.type === "start" && event.session_id) {
            setSessionId(event.session_id);
          } else if (event.type === "token") {
            setTurns((prev) =>
              prev.map((turn) =>
                turn.id === answerId
                  ? { ...turn, content: turn.content + event.content }
                  : turn,
              ),
            );
          } else if (event.type === "error") {
            setTurns((prev) =>
              prev.map((turn) =>
                turn.id === answerId ? { ...turn, content: event.content } : turn,
              ),
            );
          }
        }
      } catch (error) {
        if ((error as Error).name === "AbortError") return;
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === answerId
              ? {
                  ...turn,
                  content:
                    "Chưa kết nối được tới máy chủ. Kiểm tra backend đã chạy ở cổng 8000 chưa, rồi thử lại nhé.",
                }
              : turn,
          ),
        );
      } finally {
        setTurns((prev) =>
          prev.map((turn) =>
            turn.id === answerId
              ? {
                  ...turn,
                  followUps: FOLLOW_UPS[text] ?? DEFAULT_FOLLOW_UPS,
                }
              : turn,
          ),
        );
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, sessionId, turns],
  );

  function submit() {
    const text = input.trim();
    if (!text) return;
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    void ask(text);
  }

  function resetConversation() {
    abortRef.current?.abort();
    setTurns([]);
    setSessionId(undefined);
    setInput("");
  }

  return (
    <>
      {/* Hai nút nổi góc dưới phải */}
      {!open && (
        <div className="fixed right-[22px] bottom-[22px] z-50 flex flex-col gap-3">
          <button
            type="button"
            aria-label="Mở trợ lý AI"
            onClick={() => setOpen(true)}
            className="grid h-13 w-13 place-items-center rounded-full bg-card text-brand shadow-raised"
          >
            <ChatBubbleIcon className="h-6 w-6" />
          </button>
          <button
            type="button"
            aria-label="Mở trợ lý AI"
            onClick={() => setOpen(true)}
            className="relative grid h-13 w-13 place-items-center rounded-full bg-linear-150 from-[#3b8bff] to-brand-dark text-white shadow-raised"
          >
            <SparkleIcon className="h-[26px] w-[26px]" />
            <span className="absolute top-0.5 right-1 h-2 w-2 rounded-full bg-gold ring-2 ring-white" />
          </button>
        </div>
      )}

      {/* Panel chat */}
      {open && (
        <section
          role="dialog"
          aria-label="Trợ lý AI SalesMate"
          aria-modal="false"
          className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-card narrow:inset-auto narrow:right-[22px] narrow:bottom-[22px] narrow:h-[min(600px,88vh)] narrow:w-[376px] narrow:rounded-2xl narrow:shadow-panel"
        >
          <header className="flex items-center gap-2.5 bg-linear-150 from-brand to-brand-dark px-4 py-3.5 text-white">
            <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-full bg-white/20">
              <SparkleSmallIcon className="h-[19px] w-[19px]" />
            </span>
            <div>
              <strong className="block text-[15px] leading-tight font-semibold">
                Trợ lý AI
              </strong>
              <span className="text-[11px] opacity-85">SalesMate</span>
            </div>
            <button
              type="button"
              aria-label="Đóng trợ lý"
              onClick={() => setOpen(false)}
              className="ml-auto p-1 opacity-90 hover:opacity-100"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
          </header>

          <div
            ref={bodyRef}
            aria-live="polite"
            className="flex flex-1 flex-col gap-3.5 overflow-y-auto bg-page p-4"
          >
            {turns.length === 0 && (
              <>
                <p className="rounded-xl border border-line bg-card px-3.5 py-3 text-[13.5px]">
                  Xin chào 👋 <strong className="text-brand">Trợ lý AI SalesMate</strong>{" "}
                  có thể giúp bạn tư vấn giá, tìm bất động sản phù hợp, giải đáp
                  pháp lý và soạn tin đăng.
                </p>
                <div className="flex flex-wrap gap-2">
                  {QUICK_ACTIONS.map((action) => (
                    <button
                      key={action}
                      type="button"
                      onClick={() => void ask(action)}
                      className="rounded-full border border-line bg-card px-3 py-[7px] text-[12.5px] font-medium hover:border-brand hover:bg-[#f5f9ff] hover:text-brand"
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </>
            )}

            {turns.map((turn, index) =>
              turn.role === "user" ? (
                <p
                  key={turn.id}
                  className="max-w-[82%] self-end rounded-[14px] rounded-br-sm bg-[#e7edf5] px-3.5 py-2.5 text-[13.5px]"
                >
                  {turn.content}
                </p>
              ) : (
                <div key={turn.id}>
                  {turn.content ? (
                    <div className="ai-prose text-[13.5px] leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {turn.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <span
                      className="flex w-fit gap-1 rounded-xl border border-line bg-card px-3.5 py-[11px]"
                      aria-label="Trợ lý đang soạn câu trả lời"
                    >
                      {[0, 1, 2].map((dot) => (
                        <i
                          key={dot}
                          className="typing-dot h-1.5 w-1.5 rounded-full bg-faint"
                        />
                      ))}
                    </span>
                  )}

                  {/* Chip hỏi tiếp — chỉ hiện ở câu trả lời cuối, khi đã xong */}
                  {turn.followUps && index === turns.length - 1 && !busy && (
                    <div className="mt-1 flex flex-col gap-[7px]">
                      {turn.followUps.map((followUp) => (
                        <button
                          key={followUp}
                          type="button"
                          onClick={() => void ask(followUp)}
                          className="flex items-center gap-2 rounded-[10px] border border-line bg-card px-3 py-2.5 text-left text-[12.5px] font-medium hover:border-brand hover:bg-[#f5f9ff] hover:text-brand"
                        >
                          <span>{followUp}</span>
                          <ArrowRightIcon className="ml-auto h-[15px] w-[15px]" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ),
            )}
          </div>

          <div className="border-t border-line bg-card px-3 py-2.5">
            <div className="flex items-end gap-2 rounded-xl border border-line bg-page py-1.5 pr-1.5 pl-3">
              <textarea
                ref={inputRef}
                rows={1}
                maxLength={MAX_CHARS}
                value={input}
                placeholder="Tiếp tục cuộc trò chuyện"
                aria-label="Nhập câu hỏi cho trợ lý"
                className="max-h-[90px] flex-1 resize-none border-0 bg-transparent py-1.5 text-[13.5px] outline-none placeholder:text-faint"
                onChange={(event) => {
                  setInput(event.target.value);
                  event.target.style.height = "auto";
                  event.target.style.height = `${Math.min(event.target.scrollHeight, 90)}px`;
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
              />
              <button
                type="button"
                aria-label="Gửi câu hỏi"
                disabled={busy || !input.trim()}
                onClick={submit}
                className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[9px] bg-brand text-white disabled:opacity-40"
              >
                <SendIcon className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-1.5 flex items-center gap-2.5 px-0.5">
              <button
                type="button"
                aria-label="Bắt đầu cuộc trò chuyện mới"
                onClick={resetConversation}
                className="grid p-0.5 text-faint hover:text-brand"
              >
                <RefreshIcon className="h-4 w-4" />
              </button>
              <span className="ml-auto font-mono text-[11px] text-faint">
                {input.length} / {MAX_CHARS}
              </span>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
