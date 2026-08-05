import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

/**
 * Chặn route ở phía client cho gọn trải nghiệm. Không phải lớp bảo mật —
 * backend mới là nơi thực thi (mọi route admin đều có require_admin).
 */
export default function ProtectedRoute({ children, adminOnly = false, saleOnly = false }) {
  const { user, loading, isAdmin } = useAuth();
  const location = useLocation();

  if (loading) return <div className="loading">Đang kiểm tra phiên đăng nhập…</div>;

  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;

  if (adminOnly && !isAdmin) {
    return (
      <div className="wrap">
        <div className="page-head">
          <h1>Không có quyền truy cập</h1>
          <p>Trang này chỉ dành cho quản trị viên. Quay lại trang tìm kiếm căn hộ để tiếp tục.</p>
        </div>
      </div>
    );
  }

  if (saleOnly && isAdmin) {
    return (
      <div className="wrap">
        <div className="page-head">
          <h1>Trang dành cho nhân viên sale</h1>
          <p>
            Tài khoản quản trị không có lịch sử bán riêng. Xem toàn bộ căn đã bán ở mục
            “Căn đã bán toàn hệ thống”.
          </p>
        </div>
      </div>
    );
  }

  return children;
}
