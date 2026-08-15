import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import ApartmentDetail from './pages/ApartmentDetail';
import Documents from './pages/Documents';
import Home from './pages/Home';
import Login from './pages/Login';
import MySales from './pages/MySales';
import Profile from './pages/Profile';
import Search from './pages/Search';
import Zones from './pages/Zones';
import AddApartment from './pages/admin/AddApartment';
import AddDocument from './pages/admin/AddDocument';
import AdminSales from './pages/admin/AdminSales';

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
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <Profile />
              </ProtectedRoute>
            }
          />
          <Route
            path="/my-sales"
            element={
              <ProtectedRoute saleOnly>
                <MySales />
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
