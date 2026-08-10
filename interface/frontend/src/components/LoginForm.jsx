import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { LogoMark } from './Icons';

/**
 * Phần ruột của màn đăng nhập, dùng chung cho hai chỗ: modal nổi trên trang chủ
 * và trang `/login` đầy đủ. Chỉ có một bản logic để sau này sửa một chỗ.
 *
 * `onSuccess` chạy sau khi đăng nhập xong — modal thì đóng lại, trang thì điều
 * hướng về nơi người dùng đang muốn tới.
 */
export default function LoginForm({ onSuccess, autoFocus = true }) {
  const { signIn } = useAuth();
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const me = await signIn(form.username.trim(), form.password);
      onSuccess(me);
    } catch (submitError) {
      setError(submitError.message);
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <div className="brand">
        <LogoMark />
        SalesMate
      </div>
      <p className="sub">Đăng nhập để xem tài liệu và quản lý căn đã bán.</p>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="field">
        <label htmlFor="username">Tên đăng nhập</label>
        <input
          id="username"
          required
          autoFocus={autoFocus}
          autoComplete="username"
          value={form.username}
          onChange={update('username')}
        />
      </div>

      <div className="field">
        <label htmlFor="password">Mật khẩu</label>
        <input
          id="password"
          type="password"
          required
          autoComplete="current-password"
          value={form.password}
          onChange={update('password')}
        />
      </div>

      <button className="btn btn-primary" type="submit" disabled={submitting}>
        {submitting ? 'Đang đăng nhập…' : 'Đăng nhập'}
      </button>
    </form>
  );
}
