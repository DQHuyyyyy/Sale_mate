import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import ChatSidebar from './ChatSidebar';
import Header from './Header';

/**
 * Khung chung cho mọi trang: header + nội dung + sidebar trợ lý S.
 *
 * Sidebar mở ra thì phần nội dung co lại còn 2/3 thay vì bị che — vừa xem căn hộ
 * vừa hỏi trợ lý được. Trạng thái mở nằm ở đây vì cả hai bên cùng cần biết:
 * sidebar để hiện, phần nội dung để thu hẹp và giảm số cột lưới căn hộ.
 */
export default function Layout() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <>
      <div className={chatOpen ? 'shell chat-open' : 'shell'}>
        <Header />
        <main>
          <Outlet />
        </main>
      </div>

      <ChatSidebar open={chatOpen} onToggle={() => setChatOpen((value) => !value)} />
    </>
  );
}
