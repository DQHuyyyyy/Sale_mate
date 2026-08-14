import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { createSale, getApartment } from '../api';
import { BackIcon, HouseIcon } from '../components/Icons';
import { useAuth } from '../context/AuthContext';
import { formatArea, formatPrice, orDash } from '../utils/format';

function SellModal({ apartment, onClose, onSold }) {
  const [form, setForm] = useState({ customerName: '', customerPhone: '', soldPrice: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const update = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      await createSale({ maCan: apartment.ma_can, ...form });
      onSold();
    } catch (submitError) {
      setError(submitError.message);
      setSaving(false);
    }
  };

  return (
    <div className="modal-bg" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <form className="modal" onSubmit={submit}>
        <h3>Ghi nhận đã bán căn {apartment.ma_can}</h3>
        <p className="sub">
          Căn sẽ chuyển sang trạng thái “Đã bán” và không còn hiện trong kết quả tìm kiếm.
        </p>

        {error && <div className="alert alert-error">{error}</div>}

        <div className="field">
          <label htmlFor="customerName">Tên khách hàng</label>
          <input id="customerName" value={form.customerName} onChange={update('customerName')} />
        </div>
        <div className="field">
          <label htmlFor="customerPhone">Điện thoại khách</label>
          <input id="customerPhone" value={form.customerPhone} onChange={update('customerPhone')} />
        </div>
        <div className="field">
          <label htmlFor="soldPrice">Giá bán thực tế (tỷ VND)</label>
          <input
            id="soldPrice"
            type="number"
            step="0.001"
            min="0"
            max="20"
            placeholder={apartment.gia_tri ?? ''}
            value={form.soldPrice}
            onChange={update('soldPrice')}
          />
          <div className="hint">Bỏ trống thì lấy đúng giá niêm yết.</div>
        </div>

        <div className="form-actions">
          <button className="btn btn-primary" type="submit" disabled={saving}>
            {saving ? 'Đang lưu…' : 'Xác nhận đã bán'}
          </button>
          <button className="btn btn-ghost" type="button" onClick={onClose} disabled={saving}>
            Huỷ
          </button>
        </div>
      </form>
    </div>
  );
}

export default function ApartmentDetail() {
  const { maCan } = useParams();
  const { isSale } = useAuth();
  const [apartment, setApartment] = useState(null);
  // Ảnh đang xem nằm ở URL (`?anh=2`) chứ không phải state nội bộ, vì widget trợ
  // lý cũng cần biết — nó lấy đúng tấm này làm ngữ cảnh sửa ảnh. Sidebar và
  // trang nội dung là hai nhánh anh em dưới Layout, không truyền prop cho nhau
  // được; URL là kênh sẵn có mà cả hai cùng đọc, lại chia sẻ link được.
  const [thamSo, datThamSo] = useSearchParams();
  const activeImage = Math.max(0, Number(thamSo.get('anh')) || 0);
  const setActiveImage = (chiSo) =>
    datThamSo(chiSo > 0 ? { anh: String(chiSo) } : {}, { replace: true });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sellOpen, setSellOpen] = useState(false);
  const [sold, setSold] = useState('');

  const load = () => {
    setLoading(true);
    getApartment(maCan)
      // KHÔNG đặt lại về ảnh 0 ở đây: mở thẳng link `/apartments/X?anh=2` thì
      // phải giữ đúng tấm người ta gửi cho nhau. Sang căn khác là URL đổi và
      // tham số tự mất, nên không cần tự dọn.
      .then(setApartment)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [maCan]);

  if (loading) return <div className="loading">Đang tải thông tin căn hộ…</div>;
  if (error) {
    return (
      <div className="wrap">
        <div className="alert alert-error" style={{ marginTop: 26 }}>
          {error}
        </div>
        <Link className="back-link" to="/">
          <BackIcon style={{ width: 15, height: 15 }} />
          Về trang tìm kiếm
        </Link>
      </div>
    );
  }

  const images = apartment.images ?? [];
  // Kẹp về khoảng hợp lệ: `?anh=99` là URL người dùng gõ tay, không được nổ.
  const current = images[Math.min(activeImage, images.length - 1)];
  const canSell = isSale && apartment.tinh_trang === 'Còn';

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>
          Căn <span className="mono">{apartment.ma_can}</span>
        </h1>
        <p>
          Tòa {orDash(apartment.toa)}
          {apartment.tang !== null && apartment.tang !== undefined ? ` · Tầng ${apartment.tang}` : ''}
          {apartment.so_phong ? ` · Phòng ${apartment.so_phong}` : ''}
        </p>
      </div>

      {sold && <div className="alert alert-ok">{sold}</div>}

      <div className="detail-grid">
        <div>
          <div className={current?.image_url ? 'gallery-main' : 'gallery-main no-photo'}>
            {current?.image_url ? (
              <img src={current.image_url} alt={`Ảnh căn ${apartment.ma_can}`} />
            ) : (
              <HouseIcon />
            )}
          </div>

          {images.length > 1 && (
            <div className="gallery-thumbs">
              {images.map((image, index) => (
                <button
                  key={image.id}
                  className={index === activeImage ? 'on' : ''}
                  onClick={() => setActiveImage(index)}
                  aria-label={`Ảnh ${index + 1}`}
                >
                  <img src={image.image_url} alt="" />
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="lprice" style={{ fontSize: 24 }}>
            {formatPrice(apartment.gia, apartment.gia_tri)}
          </div>
          <div className="ltype" style={{ fontSize: 15 }}>
            {orDash(apartment.loai_can)}
          </div>
          <span className={apartment.tinh_trang === 'Còn' ? 'ltag' : 'ltag'}>
            {apartment.tinh_trang}
          </span>

          <dl className="spec-list">
            <div>
              <dt>Diện tích</dt>
              <dd>{formatArea(apartment.dien_tich, apartment.dien_tich_so)}</dd>
            </div>
            <div>
              <dt>Hướng phong thủy</dt>
              <dd>{orDash(apartment.huong)}</dd>
            </div>
            <div>
              <dt>Sổ đỏ</dt>
              <dd>{orDash(apartment.so_do)}</dd>
            </div>
            <div>
              <dt>Nội thất</dt>
              <dd>{orDash(apartment.noi_that)}</dd>
            </div>
            <div style={{ gridColumn: '1/-1' }}>
              <dt>View</dt>
              <dd>{orDash(apartment.view)}</dd>
            </div>
          </dl>

          {canSell && (
            <div className="form-actions">
              <button className="btn btn-primary" onClick={() => setSellOpen(true)}>
                Ghi nhận đã bán
              </button>
            </div>
          )}
        </div>
      </div>

      <Link className="back-link" to="/">
        <BackIcon style={{ width: 15, height: 15 }} />
        Về trang tìm kiếm
      </Link>

      {sellOpen && (
        <SellModal
          apartment={apartment}
          onClose={() => setSellOpen(false)}
          onSold={() => {
            setSellOpen(false);
            setSold(`Đã ghi nhận bán căn ${apartment.ma_can}. Xem lại ở “Lịch sử bán của tôi”.`);
            load();
          }}
        />
      )}
    </div>
  );
}
