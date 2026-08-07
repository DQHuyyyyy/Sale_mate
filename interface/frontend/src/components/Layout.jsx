import { Outlet } from 'react-router-dom';
import ChatbotWidget from './ChatbotWidget';
import Header from './Header';

/** Khung chung cho mọi trang sau đăng nhập: header + nội dung + trợ lý S. */
export default function Layout() {
  return (
    <>
      <Header />
      <main>
        <Outlet />
      </main>
      <ChatbotWidget />
    </>
  );
}
