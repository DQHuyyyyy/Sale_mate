import { useAuth } from '../context/AuthContext';
import { formatDateTime, orDash } from '../utils/format';

export default function Profile() {
  const { user, isAdmin } = useAuth();
  if (!user) return null;

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Profile cá nhân</h1>
        <p>Thông tin tài khoản đang đăng nhập.</p>
      </div>

      <div className="panel">
        <dl className="spec-list">
          <div>
            <dt>Họ tên</dt>
            <dd>{user.full_name}</dd>
          </div>
          <div>
            <dt>Tên đăng nhập</dt>
            <dd className="mono">@{user.username}</dd>
          </div>
          <div>
            <dt>Vai trò</dt>
            <dd>{isAdmin ? 'Quản trị viên' : 'Nhân viên Sale'}</dd>
          </div>
          <div>
            <dt>Điện thoại</dt>
            <dd>{orDash(user.phone)}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{orDash(user.email)}</dd>
          </div>
          <div>
            <dt>Ngày tạo tài khoản</dt>
            <dd>{formatDateTime(user.created_at)}</dd>
          </div>
        </dl>
        <p className="hint" style={{ marginTop: 16 }}>
          Cần đổi thông tin hoặc mật khẩu thì báo quản trị viên — chức năng tự sửa chưa mở.
        </p>
      </div>
    </div>
  );
}
