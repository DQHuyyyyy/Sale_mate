import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import AvatarMenu from './AvatarMenu';
import LoginModal from './LoginModal';
import MenuSoDo from './MenuSoDo';
import { BurgerIcon, FileIcon, HouseIcon, LogoMark, MapIcon, NewspaperIcon, SearchIcon } from './Icons';

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
              <HouseIcon />
              Trang chủ
            </NavLink>
            <NavLink
              to="/tim-kiem"
              className={({ isActive }) => (isActive ? 'on' : '')}
              onClick={closeNav}
            >
              <SearchIcon />
              Tìm kiếm căn hộ
            </NavLink>
            {/* Mục này KHÔNG còn là một link đơn: Ocean City có ba dự án
                thành phần, mỗi cái một sơ đồ riêng. Menu thả xuống nói ra điều
                đó ngay ở thanh điều hướng, thay vì bắt vào một trang trung gian
                rồi chọn tiếp. */}
            <MenuSoDo lopNut="hd-so-do" khiChon={closeNav}>
              <MapIcon />
              Sơ đồ phân khu
            </MenuSoDo>
            <NavLink
              to="/tin-tuc"
              className={({ isActive }) => (isActive ? 'on' : '')}
              onClick={closeNav}
            >
              <NewspaperIcon />
              Tin tức
            </NavLink>


            {/* Tài liệu là kho nội bộ của đội sale — khách không thấy mục này,
                và backend cũng chặn nếu gọi thẳng API.

                Trỏ `/tai-lieu` chứ KHÔNG phải `/documents`: đây là 11 tài liệu
                trợ lý thật sự đọc và trích nguồn, tức thứ người dùng bấm vào
                menu để tìm. `/documents` là kho file admin tải lên — việc khác,
                vào từ chính trang này. Hai trang từng cùng tên "Tài liệu" và
                menu trỏ nhầm sang kho file, nên 11 tài liệu không có lối vào
                nào ngoài nút trích nguồn trong khung chat. */}
            {user && (
              <NavLink
                to="/tai-lieu"
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
