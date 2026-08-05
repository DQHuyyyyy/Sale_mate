import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import ApartmentDetail from './pages/ApartmentDetail';
import Documents from './pages/Documents';
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

        {/* Mọi trang dưới đây đều phải đăng nhập. Route admin chặn thêm theo role. */}
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/" element={<Search />} />
          <Route path="/zones" element={<Zones />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/apartments/:maCan" element={<ApartmentDetail />} />
          <Route path="/profile" element={<Profile />} />
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
