import { useState } from 'react';
import { datCoc } from '../api';
import { formatPrice } from '../utils/format';

/**
 * Form giữ chỗ một căn. Mở từ nút "Đặt cọc" ở trang chi tiết.
 *
 * KHÔNG đòi đăng nhập: khách vãng lai đang xem căn là người sẵn sàng nhất để
 * lại số, bắt họ tạo tài khoản trước là chặn đúng lúc không nên chặn.
 *
 * Chỉ xin họ tên và số điện thoại. Không hỏi CMND, không hỏi địa chỉ — thu thêm
 * dữ liệu cá nhân mà chưa dùng đến là rủi ro không đổi lấy được gì.
 *
 * ⚠️ Không nêu số tiền cọc, thời hạn giữ chỗ hay mức phạt ở bất kỳ đâu trong
 * form này. Hệ thống không có dữ liệu nào về chúng — cùng luật với tool `dat_coc`
 * của trợ lý.
 */
export default function DatCocModal({ apartment, onClose, onDone }) {
  const [form, setForm] = useState({ hoTen: '', soDienThoai: '', ghiChu: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const ketQua = await datCoc({ maCan: apartment.ma_can, ...form });
      onDone(ketQua.loi_nhan);
    } catch (submitError) {
      setError(submitError.message);
      setSaving(false);
    }
  };

  return (
    <div className="modal-bg" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <form className="modal" onSubmit={submit}>
        <h3>Giữ chỗ căn {apartment.ma_can}</h3>
        <p className="sub">
          {formatPrice(apartment.gia, apartment.gia_tri)} · {apartment.loai_can || 'Căn hộ'}
          {apartment.phan_khu ? ` · ${apartment.phan_khu}` : ''}
        </p>
        <p className="sub">
          Để lại số điện thoại, đội sale sẽ gọi lại để trao đổi chi tiết và xác nhận cọc.
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <div className="field">
          <label htmlFor="dcHoTen">Họ tên</label>
          <input id="dcHoTen" value={form.hoTen} onChange={update('hoTen')} autoComplete="name" />
        </div>
        <div className="field">
          <label htmlFor="dcSdt">
            Số điện thoại <span aria-hidden="true">*</span>
          </label>
          <input
            id="dcSdt"
            required
            inputMode="tel"
            autoComplete="tel"
            placeholder="09xxxxxxxx"
            value={form.soDienThoai}
            onChange={update('soDienThoai')}
          />
        </div>
        <div className="field">
          <label htmlFor="dcGhiChu">Ghi chú</label>
          <textarea
            id="dcGhiChu"
            rows={3}
            maxLength={500}
            placeholder="Thời gian tiện nhận cuộc gọi, yêu cầu riêng…"
            value={form.ghiChu}
            onChange={update('ghiChu')}
          />
        </div>

        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>
            Huỷ
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Đang gửi…' : 'Gửi yêu cầu giữ chỗ'}
          </button>
        </div>
      </form>
    </div>
  );
}
