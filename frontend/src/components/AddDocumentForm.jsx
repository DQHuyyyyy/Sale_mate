import { useState } from 'react';
import { addDocument } from '../api';

const CATEGORIES = ['Pháp lý', 'Bảng giá', 'Chính sách', 'Khác'];

/** Form thêm tài liệu (admin). Hoặc chọn file, hoặc dán link có sẵn. */
export default function AddDocumentForm() {
  const [form, setForm] = useState({ title: '', description: '', category: '', fileUrl: '' });
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setDone('');

    if (!file && !form.fileUrl.trim()) {
      setError('Cần chọn file tải lên hoặc điền đường dẫn tài liệu.');
      return;
    }

    setSaving(true);
    try {
      const created = await addDocument({
        title: form.title.trim(),
        description: form.description.trim(),
        category: form.category,
        fileUrl: form.fileUrl.trim(),
        file,
      });
      setDone(`Đã thêm tài liệu “${created.title}”.`);
      setForm({ title: '', description: '', category: '', fileUrl: '' });
      setFile(null);
      event.target.reset();
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Thêm tài liệu</h2>
      <p className="sub">Tài liệu hiện cho mọi tài khoản đã đăng nhập xem.</p>

      {error && <div className="alert alert-error">{error}</div>}
      {done && <div className="alert alert-ok">{done}</div>}

      <div className="form-grid">
        <div className="field full">
          <label htmlFor="title">Tiêu đề *</label>
          <input id="title" required maxLength={200} value={form.title} onChange={update('title')} />
        </div>
        <div className="field">
          <label htmlFor="category">Nhóm tài liệu</label>
          <select id="category" value={form.category} onChange={update('category')}>
            <option value="">Chưa phân nhóm</option>
            {CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="file">File tài liệu</label>
          <input id="file" type="file" onChange={(event) => setFile(event.target.files[0] ?? null)} />
          <div className="hint">Tối đa 20MB. Backend đẩy lên Supabase Storage.</div>
        </div>
        <div className="field full">
          <label htmlFor="fileUrl">Hoặc đường dẫn có sẵn</label>
          <input
            id="fileUrl"
            value={form.fileUrl}
            onChange={update('fileUrl')}
            placeholder="https://…"
          />
        </div>
        <div className="field full">
          <label htmlFor="description">Mô tả</label>
          <textarea id="description" rows={3} value={form.description} onChange={update('description')} />
        </div>
      </div>

      <div className="form-actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Đang lưu…' : 'Thêm tài liệu'}
        </button>
      </div>
    </form>
  );
}
