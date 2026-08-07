import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import AvatarMenu from './AvatarMenu';
import { BurgerIcon, FileIcon, LogoMark, MapIcon, SearchIcon } from './Icons';

export default function Header() {
  const [navOpen, setNavOpen] = useState(false);
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
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'on' : '')} onClick={closeNav}>
              <SearchIcon />
              Tìm kiếm căn hộ
            </NavLink>
            <NavLink to="/zones" className={({ isActive }) => (isActive ? 'on' : '')} onClick={closeNav}>
              <MapIcon />
              Sơ đồ phân khu
            </NavLink>
            <NavLink
              to="/documents"
              className={({ isActive }) => (isActive ? 'on' : '')}
              onClick={closeNav}
            >
              <FileIcon />
              Tài liệu
            </NavLink>
          </nav>

          <AvatarMenu />
        </div>
      </header>
    </div>
  );
}
