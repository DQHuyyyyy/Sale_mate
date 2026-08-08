import { useEffect, useRef, useState } from 'react';
import { sendChatMessage } from '../api';
import { CloseIcon, SendIcon } from './Icons';

const QUICK_ASKS = ['Căn 2PN dưới 4 tỷ', 'Căn còn ở tòa S1', 'Tư vấn view đẹp'];

/**
 * Trợ lý S — sidebar bên phải, thu gọn thành nút tròn chữ "S".
 *
 * Mở được cho cả khách chưa đăng nhập. Backend giới hạn số lượt theo IP nên khi
 * hỏi quá nhanh sẽ nhận lỗi 429 kèm số giây phải đợi — hiện nguyên văn câu đó
 * cho người dùng, không nuốt đi.
 *
 * Giữ lịch sử hội thoại trong state và gửi kèm mỗi lượt, đúng contract
 * POST /api/chat {message, history} -> {reply}.
 */
export default function ChatSidebar({ open, onToggle }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, sending]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const ask = async (text) => {
    const message = text.trim();
    if (!message || sending) return;

    // history gửi lên là hội thoại TRƯỚC câu này, và bỏ các bong bóng lỗi.
    const history = messages
      .filter((item) => !item.error)
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setInput('');
    setSending(true);

    try {
      const data = await sendChatMessage(message, history);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', content: error.message, error: true }]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      ask(input);
    }
  };

  if (!open) {
    return (
      <div className="fab">
        <button aria-label="Mở trợ lý S" onClick={onToggle}>
          S
        </button>
      </div>
    );
  }

  return (
    <aside className="chat-sidebar" aria-label="Trợ lý S">
      <div className="cw-hd">
        <div className="ava">S</div>
        <div>
          <b>Trợ lý S</b>
          <span>SalesMate AI</span>
        </div>
        <div className="acts">
          <button aria-label="Thu gọn trợ lý" onClick={onToggle}>
            <CloseIcon />
          </button>
        </div>
      </div>

      <div className="cw-body" ref={bodyRef} aria-live="polite">
        <div className="cw-greet">
          Xin chào 👋 <b>Trợ lý S</b> giúp bạn tìm căn phù hợp, tra thông tin căn hộ và hỗ trợ tư
          vấn khách.
        </div>

        {messages.length === 0 && (
          <div className="qa">
            {QUICK_ASKS.map((text) => (
              <button key={text} onClick={() => ask(text)}>
                {text}
              </button>
            ))}
          </div>
        )}

        {messages.map((item, index) => (
          <div
            key={index}
            className={item.role === 'user' ? 'cmsg u' : item.error ? 'cmsg a err' : 'cmsg a'}
          >
            {item.content}
          </div>
        ))}

        {sending && (
          <div className="ctyping">
            <i />
            <i />
            <i />
          </div>
        )}
      </div>

      <div className="cw-foot">
        <div className="cw-inrow">
          <textarea
            ref={inputRef}
            rows={1}
            maxLength={2000}
            placeholder="Nhập câu hỏi cho Trợ lý S…"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className="cw-send"
            aria-label="Gửi"
            disabled={sending || !input.trim()}
            onClick={() => ask(input)}
          >
            <SendIcon />
          </button>
        </div>
      </div>
    </aside>
  );
}
