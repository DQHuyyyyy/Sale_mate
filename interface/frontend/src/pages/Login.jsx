import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import LoginForm from '../components/LoginForm';
import { useAuth } from '../context/AuthContext';

/**
 * Trang đăng nhập đầy đủ tại `/login`.
 *
 * Lối vào chính giờ là modal nổi trên trang (nút "Đăng nhập" ở header). Trang
 * này vẫn giữ cho hai trường hợp: mở thẳng link `/login`, và khi khách bấm vào
 * một trang nội bộ nên `ProtectedRoute` đá về đây.
 */
export default function Login() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const quayVe = location.state?.from || '/';

  if (loading) return <div className="loading">Đang kiểm tra phiên đăng nhập…</div>;
  if (user) return <Navigate to={quayVe} replace />;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <LoginForm onSuccess={() => navigate(quayVe, { replace: true })} />
      </div>
    </div>
  );
}
