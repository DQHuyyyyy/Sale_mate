import { useEffect } from 'react';
import LoginForm from './LoginForm';
import { CloseIcon } from './Icons';

/**
 * Đăng nhập nổi ngay trên trang đang xem — khách không bị đá sang trang khác,
 * đăng nhập xong vẫn ở nguyên chỗ cũ.
 *
 * Đóng bằng nút X, phím Esc, hoặc bấm ra ngoài.
 */
export default function LoginModal({ onClose }) {
  useEffect(() => {
    const onEscape = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onEscape);
    // Khoá cuộn nền để trang phía sau không trôi khi người dùng lăn chuột.
    const scrollCu = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onEscape);
      document.body.style.overflow = scrollCu;
    };
  }, [onClose]);

  return (
    <div
      className="modal-bg"
      role="dialog"
      aria-modal="true"
      aria-label="Đăng nhập"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div className="auth-card auth-modal">
        <button className="auth-modal-close" aria-label="Đóng" onClick={onClose}>
          <CloseIcon />
        </button>
        <LoginForm onSuccess={onClose} />
      </div>
    </div>
  );
}
