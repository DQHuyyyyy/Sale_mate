import { useState } from 'react';
import { createSaleAccount } from '../api';

const EMPTY = { username: '', password: '', fullName: '', phone: '', email: '' };

/**
 * Form tạo tài khoản sale (admin).
 * Mật khẩu do admin đặt và bàn giao cho nhân viên — chưa có chức năng tự đổi
 * mật khẩu, xem TIENDO.md.
 */
export default function AddSaleForm({ onCreated, onCancel }) {
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      const created = await createSaleAccount(form);
      setForm(EMPTY);
      onCreated(created);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Thêm tài khoản Sale</h2>
      <p className="sub">
        Tài khoản tạo ở đây luôn có vai trò sale. Nhớ báo lại mật khẩu cho nhân viên.
      </p>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="form-grid">
        <div className="field">
          <label htmlFor="username">Tên đăng nhập *</label>
          <input
            id="username"
            required
            minLength={3}
            maxLength={50}
            pattern="[a-zA-Z0-9._\-]+"
            title="Chỉ dùng chữ không dấu, số và các ký tự . _ -"
            value={form.username}
            onChange={update('username')}
            placeholder="sale02"
          />
          <div className="hint">Chữ không dấu, số và . _ - ; tối thiểu 3 ký tự.</div>
        </div>
        <div className="field">
          <label htmlFor="fullName">Họ tên *</label>
          <input
            id="fullName"
            required
            maxLength={100}
            value={form.fullName}
            onChange={update('fullName')}
            placeholder="Nguyễn Văn A"
          />
        </div>
        <div className="field">
          <label htmlFor="password">Mật khẩu *</label>
          <input
            id="password"
            type="password"
            required
            minLength={6}
            autoComplete="new-password"
            value={form.password}
            onChange={update('password')}
          />
          <div className="hint">Tối thiểu 6 ký tự.</div>
        </div>
        <div className="field">
          <label htmlFor="phone">Điện thoại</label>
          <input id="phone" maxLength={20} value={form.phone} onChange={update('phone')} />
        </div>
        <div className="field full">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            maxLength={100}
            value={form.email}
            onChange={update('email')}
          />
        </div>
      </div>

      <div className="form-actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Đang tạo…' : 'Tạo tài khoản'}
        </button>
        <button className="btn btn-ghost" type="button" onClick={onCancel} disabled={saving}>
          Huỷ
        </button>
      </div>
    </form>
  );
}
