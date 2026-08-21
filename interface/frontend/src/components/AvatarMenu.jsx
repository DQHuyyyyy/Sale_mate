import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  ChartIcon,
  ClockIcon,
  FileIcon,
  HouseIcon,
  LogoutIcon,
  UserIcon,
  UsersIcon,
} from './Icons';

/** Chữ cái đầu của họ tên, tối đa 2 ký tự — hiện trong nút avatar. */
function initials(fullName) {
  const parts = (fullName || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Menu avatar. Mục hiện ra khác nhau theo role — đây chỉ là UX,
 * bảo mật thật do backend chặn.
 */
export default function AvatarMenu() {
  const { user, isAdmin, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return undefined;
    const onDocumentClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    };
    const onEscape = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('click', onDocumentClick);
    document.addEventListener('keydown', onEscape);
    return () => {
      document.removeEventListener('click', onDocumentClick);
      document.removeEventListener('keydown', onEscape);
    };
  }, [open]);

  if (!user) return null;

  const close = () => setOpen(false);

  const handleSignOut = () => {
    close();
    signOut();
    // Về trang chủ, không phải màn đăng nhập: website xem được khi chưa đăng
    // nhập, nên đăng xuất xong vẫn tra cứu căn hộ bình thường.
    navigate('/', { replace: true });
  };

  return (
    <div className="hd-right" ref={containerRef}>
      <button
        className="avatar"
        aria-label="Tài khoản"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        {initials(user.full_name)}
      </button>

      {open && (
        <div className="menu">
          <div className="me">
            <b>{user.full_name}</b>
            <span>
              {isAdmin ? 'Quản trị viên' : 'Nhân viên Sale'} · @{user.username}
            </span>
          </div>

          {/* Một mục cho cả hai vai. Trước đây là ba mục ("Lịch sử bán của
              tôi", "Lead đặt cọc", "Căn đã bán toàn hệ thống") trỏ tới ba chỗ
              nói về cùng một phễu bán hàng. */}
          <Link to="/giao-dich" onClick={close}>
            <ClockIcon />
            Giao dịch
          </Link>

          {isAdmin && (
            <>
              <div className="grp">Quản trị</div>
              <Link to="/admin/sales" onClick={close}>
                <UsersIcon />
                Quản lý Sale
              </Link>
              <Link to="/admin/apartments/new" onClick={close}>
                <HouseIcon />
                Thêm căn hộ
              </Link>
              <Link to="/admin/documents/new" onClick={close}>
                <FileIcon />
                Thêm tài liệu
              </Link>
            </>
          )}

          <div className="grp">Tài khoản</div>
          <Link to="/profile" onClick={close}>
            <UserIcon />
            Profile cá nhân
          </Link>
          <button type="button" className="menu-item" onClick={handleSignOut}>
            <LogoutIcon />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
