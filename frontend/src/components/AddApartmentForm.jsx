import { useState } from 'react';
import { addApartment, uploadApartmentImages } from '../api';

const EMPTY = {
  ma_can: '',
  toa: '',
  tang: '',
  so_phong: '',
  loai_can: '',
  dien_tich_so: '',
  gia_tri: '',
  huong: '',
  view: '',
  so_do: '',
  noi_that: '',
};

/**
 * Form thêm căn hộ (admin).
 * Giá và diện tích nhập bằng SỐ — backend tự sinh chuỗi hiển thị ("1,8 tỷ",
 * "28m2") nên cột text và cột số không bao giờ lệch nhau.
 * Ảnh upload ở bước 2 vì backend cần mã căn đã tồn tại mới gắn ảnh được.
 */
export default function AddApartmentForm() {
  const [form, setForm] = useState(EMPTY);
  const [files, setFiles] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setDone('');
    setSaving(true);

    try {
      await addApartment({
        ma_can: form.ma_can.trim(),
        toa: form.toa.trim(),
        tang: form.tang === '' ? null : Number(form.tang),
        so_phong: form.so_phong === '' ? null : Number(form.so_phong),
        loai_can: form.loai_can.trim() || null,
        dien_tich_so: Number(form.dien_tich_so),
        gia_tri: Number(form.gia_tri),
        huong: form.huong.trim() || null,
        view: form.view.trim() || null,
        so_do: form.so_do.trim() || null,
        noi_that: form.noi_that.trim() || null,
        tinh_trang: 'Còn',
        image_urls: [],
      });

      if (files.length) {
        // Căn đã tạo xong; ảnh hỏng thì báo riêng, không xoá căn vừa thêm.
        try {
          await uploadApartmentImages(form.ma_can.trim(), files);
        } catch (uploadError) {
          setDone(`Đã thêm căn ${form.ma_can.trim()}, nhưng ảnh chưa lên được.`);
          setError(uploadError.message);
          setForm(EMPTY);
          setFiles([]);
          return;
        }
      }

      setDone(`Đã thêm căn ${form.ma_can.trim()}.`);
      setForm(EMPTY);
      setFiles([]);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Thêm căn hộ</h2>
      <p className="sub">Căn mới mặc định ở trạng thái “Còn” và hiện ngay trong kết quả tìm kiếm.</p>

      {error && <div className="alert alert-error">{error}</div>}
      {done && <div className="alert alert-ok">{done}</div>}

      <div className="form-grid">
        <div className="field">
          <label htmlFor="ma_can">Mã căn *</label>
          <input id="ma_can" required value={form.ma_can} onChange={update('ma_can')} placeholder="VOP103" />
        </div>
        <div className="field">
          <label htmlFor="toa">Tòa *</label>
          <input id="toa" required value={form.toa} onChange={update('toa')} placeholder="S1" />
        </div>
        <div className="field">
          <label htmlFor="tang">Tầng</label>
          <input id="tang" type="number" min="0" max="200" value={form.tang} onChange={update('tang')} />
        </div>
        <div className="field">
          <label htmlFor="so_phong">Số phòng trên tầng</label>
          <input id="so_phong" type="number" value={form.so_phong} onChange={update('so_phong')} placeholder="2006" />
          <div className="hint">Mã phòng theo tầng, không phải số phòng ngủ.</div>
        </div>
        <div className="field">
          <label htmlFor="loai_can">Loại căn</label>
          <input id="loai_can" value={form.loai_can} onChange={update('loai_can')} placeholder="2 PN, 1WC" />
        </div>
        <div className="field">
          <label htmlFor="dien_tich_so">Diện tích (m²) *</label>
          <input
            id="dien_tich_so"
            type="number"
            step="0.01"
            min="1"
            required
            value={form.dien_tich_so}
            onChange={update('dien_tich_so')}
          />
        </div>
        <div className="field">
          <label htmlFor="gia_tri">Giá (tỷ VND) *</label>
          <input
            id="gia_tri"
            type="number"
            step="0.001"
            min="0"
            max="20"
            required
            value={form.gia_tri}
            onChange={update('gia_tri')}
          />
          <div className="hint">Trong khoảng 0–20 tỷ.</div>
        </div>
        <div className="field">
          <label htmlFor="huong">Hướng phong thủy</label>
          <input id="huong" value={form.huong} onChange={update('huong')} placeholder="Đông Bắc" />
        </div>
        <div className="field">
          <label htmlFor="so_do">Sổ đỏ</label>
          <input id="so_do" value={form.so_do} onChange={update('so_do')} placeholder="Sẵn sổ" />
        </div>
        <div className="field full">
          <label htmlFor="view">View</label>
          <input id="view" value={form.view} onChange={update('view')} placeholder="View công viên" />
        </div>
        <div className="field full">
          <label htmlFor="noi_that">Nội thất</label>
          <input id="noi_that" value={form.noi_that} onChange={update('noi_that')} placeholder="Full nội thất" />
        </div>
        <div className="field full">
          <label htmlFor="images">Ảnh căn hộ</label>
          <input
            id="images"
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={(event) => setFiles(Array.from(event.target.files))}
          />
          <div className="hint">
            JPG/PNG/WEBP/GIF, mỗi ảnh tối đa 8MB. Backend đẩy lên Supabase Storage.
          </div>
        </div>
      </div>

      <div className="form-actions">
        <button className="btn btn-primary" type="submit" disabled={saving}>
          {saving ? 'Đang lưu…' : 'Thêm căn hộ'}
        </button>
      </div>
    </form>
  );
}
