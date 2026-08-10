import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AvatarMenu from './AvatarMenu';
import LoginModal from './LoginModal';
import { BurgerIcon, FileIcon, LogoMark, MapIcon, SearchIcon } from './Icons';

export default function Header() {
  const [navOpen, setNavOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const { user, loading } = useAuth();

  const closeNav = () => setNavOpen(false);

  return (
    <div className={navOpen ? 'app nav-open' : 'app'}>
      {navOpen && <div className="backdrop" onClick={closeNav} />}
      <header className="app-header">
        <div className="wrap hd">
          <button className="burger" aria-label="Menu" onClick={() => setNavOpen((v) => !v)}>
            <BurgerIcon />
          </button>

          <NavLink className="logo" to="/">
            <LogoMark className="mk" />
            SalesMate
          </NavLink>

          <nav className="main">
            <NavLink
              to="/"
              end
              className={({ isActive }) => (isActive ? 'on' : '')}
              onClick={closeNav}
            >
              <SearchIcon />
              Tìm kiếm căn hộ
            </NavLink>
            <NavLink
              to="/zones"
              className={({ isActive }) => (isActive ? 'on' : '')}
              onClick={closeNav}
            >
              <MapIcon />
              Sơ đồ phân khu
            </NavLink>

            {/* Tài liệu là kho nội bộ của đội sale — khách không thấy mục này,
                và backend cũng chặn nếu gọi thẳng API. */}
            {user && (
              <NavLink
                to="/documents"
                className={({ isActive }) => (isActive ? 'on' : '')}
                onClick={closeNav}
              >
                <FileIcon />
                Tài liệu
              </NavLink>
            )}
          </nav>

          {loading ? null : user ? (
            <AvatarMenu />
          ) : (
            <div className="hd-right">
              {/* Mở modal ngay trên trang đang xem, không điều hướng đi đâu —
                  đăng nhập xong người dùng vẫn ở nguyên chỗ cũ. */}
              <button className="btn-login" onClick={() => setLoginOpen(true)}>
                Đăng nhập
              </button>
            </div>
          )}
        </div>
      </header>

      {loginOpen && <LoginModal onClose={() => setLoginOpen(false)} />}
    </div>
  );
}
