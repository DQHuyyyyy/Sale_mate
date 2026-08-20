import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getApartment } from '../api';
import { BackIcon, HouseIcon } from '../components/Icons';
import { formatArea, formatPrice, orDash } from '../utils/format';
import DatCocModal from '../components/DatCocModal';
import { conBanDuoc, lopTrangThai, nhanTrangThai } from '../utils/trangThai';

export default function ApartmentDetail() {
  const { maCan } = useParams();
  const [apartment, setApartment] = useState(null);

  // Ảnh đang xem nằm trên URL (?anh=2), KHÔNG phải state cục bộ. Trợ lý S là
  // component anh em ở sidebar, nó cần biết người dùng đang dừng ở ảnh nào để
  // tính năng "Modify Object" sửa đúng ảnh đó — state cục bộ thì nó không thấy.
  // Cùng lý do bộ lọc tìm kiếm nằm trên URL, xem đầu Search.jsx. Tiện thể link
  // chia sẻ và F5 cũng giữ đúng ảnh.
  const [searchParams, setSearchParams] = useSearchParams();
  const activeImage = Math.max(0, Number(searchParams.get('anh') ?? 0) || 0);
  const setActiveImage = (index) => {
    const params = new URLSearchParams(searchParams);
    if (index > 0) params.set('anh', String(index));
    else params.delete('anh');
    // `replace` để nút Back của trình duyệt không phải lùi qua từng ảnh đã xem.
    setSearchParams(params, { replace: true });
  };
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [datCocOpen, setDatCocOpen] = useState(false);
  const [thongBao, setThongBao] = useState('');

  const load = () => {
    setLoading(true);
    getApartment(maCan)
      .then((data) => {
        setApartment(data);
        setActiveImage(0);
      })
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
        <Link className="back-link" to="/tim-kiem">
          <BackIcon style={{ width: 15, height: 15 }} />
          Về trang tìm kiếm
        </Link>
      </div>
    );
  }

  const images = apartment.images ?? [];
  // Kẹp chỉ số: URL do người dùng sửa được, `?anh=99` không được làm mất
  // ảnh chính thành khung trống.
  const chiSoAnh = images.length ? Math.min(activeImage, images.length - 1) : 0;
  const current = images[chiSoAnh];
  // Nút đặt cọc hiện cho MỌI người xem, kể cả khách chưa đăng nhập — đó là cả
  // mục đích của nó. Chỉ ẩn khi căn không còn nhận giữ chỗ được nữa.
  //
  // KHÔNG có nút "Ghi nhận đã bán" ở đây nữa: chốt bán chỉ diễn ra ở màn Giao
  // dịch, bằng cách chốt một lead — chỗ đó đã có sẵn tên và số điện thoại người
  // mua, không bắt gõ lại.
  const coTheDatCoc = conBanDuoc(apartment.tinh_trang_chi_tiet, apartment.tinh_trang);

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>
          Căn <span className="mono">{apartment.ma_can}</span>
        </h1>
        <p>
          {/* Phân khu đứng ĐẦU: đó là thứ định vị căn trong đại đô thị, tòa/tầng
              chỉ có nghĩa khi đã biết phân khu nào. */}
          {apartment.phan_khu ? `${apartment.phan_khu} · ` : ''}
          Tòa {orDash(apartment.toa)}
          {apartment.tang !== null && apartment.tang !== undefined ? ` · Tầng ${apartment.tang}` : ''}
          {apartment.so_phong ? ` · Phòng ${apartment.so_phong}` : ''}
        </p>
      </div>

      {thongBao && <div className="alert alert-ok">{thongBao}</div>}

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
                  className={index === chiSoAnh ? 'on' : ''}
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
          <span className={`ttag ${lopTrangThai(apartment.tinh_trang_chi_tiet, apartment.tinh_trang)}`}>
            {nhanTrangThai(apartment.tinh_trang_chi_tiet, apartment.tinh_trang)}
          </span>

          <dl className="spec-list">
            <div>
              <dt>Phân khu</dt>
              <dd>{orDash(apartment.phan_khu)}</dd>
            </div>
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

          {coTheDatCoc && (
            <div className="form-actions">
              <button className="btn btn-primary" onClick={() => setDatCocOpen(true)}>
                Đặt cọc căn này
              </button>
            </div>
          )}
        </div>
      </div>

      <Link className="back-link" to="/tim-kiem">
        <BackIcon style={{ width: 15, height: 15 }} />
        Về trang tìm kiếm
      </Link>

      {datCocOpen && (
        <DatCocModal
          apartment={apartment}
          onClose={() => setDatCocOpen(false)}
          onDone={(loiNhan) => {
            setDatCocOpen(false);
            setThongBao(loiNhan);
            // Tải lại để tình trạng căn đổi sang "Đã đặt cọc" ngay trước mắt
            // khách — không có bước này thì họ vừa gửi xong vẫn thấy "Còn" và
            // tưởng yêu cầu chưa vào.
            load();
          }}
        />
      )}

    </div>
  );
}
