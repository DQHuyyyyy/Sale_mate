import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import ApartmentDetail from './pages/ApartmentDetail';
import Documents from './pages/Documents';
import Home from './pages/Home';
import Login from './pages/Login';
import News from './pages/News';
import Profile from './pages/Profile';
import Search from './pages/Search';
import SoDoPhanKhu from './pages/SoDoPhanKhu';
import Zones from './pages/Zones';
import AddApartment from './pages/admin/AddApartment';
import AddDocument from './pages/admin/AddDocument';
import AdminSales from './pages/admin/AdminSales';
import GiaoDich from './pages/GiaoDich';
import { TaiLieuAIChiTiet, TaiLieuAIDanhSach } from './pages/TaiLieuAI';

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<Layout />}>
          {/* Công khai — khách vãng lai xem được, backend cũng mở các endpoint này. */}
          <Route path="/" element={<Home />} />
          <Route path="/tim-kiem" element={<Search />} />
          <Route path="/zones" element={<Zones />} />
          {/* Sơ đồ tương tác từng dự án. Công khai như trang chủ — đây là
              thứ khách xem trước khi quyết định hỏi căn nào. */}
          <Route path="/so-do-phan-khu/:duAn" element={<SoDoPhanKhu />} />
          <Route path="/tin-tuc" element={<News />} />
          <Route path="/apartments/:maCan" element={<ApartmentDetail />} />


          {/* Nội bộ — phải đăng nhập. Route admin chặn thêm theo role.
              Đây chỉ là lớp trải nghiệm; backend mới là nơi thực thi. */}
          <Route
            path="/documents"
            element={
              <ProtectedRoute>
                <Documents />
              </ProtectedRoute>
            }
          />
          {/* Kho tài liệu trợ lý dùng để trả lời — đích của nút trích nguồn.
              Phải đăng nhập: nội dung là tài liệu nội bộ của đội bán hàng. */}
          <Route
            path="/tai-lieu"
            element={
              <ProtectedRoute>
                <TaiLieuAIDanhSach />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tai-lieu/:docId"
            element={
              <ProtectedRoute>
                <TaiLieuAIChiTiet />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <Profile />
              </ProtectedRoute>
            }
          />
          {/* Một màn cho cả hai vai: lead đặt cọc + căn đã bán là hai nửa của
              cùng một phễu. Admin thấy toàn hệ thống, sale thấy phần của mình —
              phân quyền thật nằm ở backend, đây chỉ cần đăng nhập. */}
          <Route
            path="/giao-dich"
            element={
              <ProtectedRoute>
                <GiaoDich />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/sales"
            element={
              <ProtectedRoute adminOnly>
                <AdminSales />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/apartments/new"
            element={
              <ProtectedRoute adminOnly>
                <AddApartment />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/documents/new"
            element={
              <ProtectedRoute adminOnly>
                <AddDocument />
              </ProtectedRoute>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
