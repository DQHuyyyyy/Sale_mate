import { Link } from 'react-router-dom';
import { formatArea, formatPrice } from '../utils/format';
import { AreaIcon, CompassIcon, HouseIcon } from './Icons';
import { lopTrangThai, nhanTrangThai } from '../utils/trangThai';

export default function ApartmentCard({ apartment }) {
  const {
    ma_can: maCan,
    toa,
    tang,
    loai_can: loaiCan,
    dien_tich: dienTich,
    dien_tich_so: dienTichSo,
    huong,
    view,
    so_do: soDo,
    noi_that: noiThat,
    gia,
    gia_tri: giaTri,
    tinh_trang: tinhTrang,
    tinh_trang_chi_tiet: tinhTrangChiTiet,
    phan_khu: phanKhu,
    thumbnail,
  } = apartment;

  return (
    <Link className="lcard" to={`/apartments/${encodeURIComponent(maCan)}`}>
      <div className="thumb">
        {thumbnail ? <img src={thumbnail} alt={`Ảnh căn ${maCan}`} loading="lazy" /> : <HouseIcon className="house" />}
        <span className={`badge-st ${lopTrangThai(tinhTrangChiTiet, tinhTrang)}`}>
          {nhanTrangThai(tinhTrangChiTiet, tinhTrang)}
        </span>
        <span className="badge-code">{maCan}</span>
        {/* Phân khu nằm trên ảnh: lưới bốn cột chật, thêm một dòng chữ nữa là
            thẻ cao lên và bớt căn hiện trong màn hình đầu. */}
        {phanKhu && <span className="badge-khu">{phanKhu}</span>}
      </div>

      <div className="lbody">
        <div className="lprice">{formatPrice(gia, giaTri)}</div>
        <div className="ltype">{loaiCan || 'Chưa rõ loại căn'}</div>

        <div className="lmeta">
          <span>
            <AreaIcon />
            {formatArea(dienTich, dienTichSo)}
          </span>
          <span>
            <HouseIcon />
            Tòa {toa || '—'}
            {tang !== null && tang !== undefined ? ` · T${tang}` : ''}
          </span>
          {huong && (
            <span>
              <CompassIcon />
              {huong}
            </span>
          )}
        </div>

        {view && <div className="lview">{view}</div>}

        {(soDo || noiThat) && (
          <div className="ltags">
            {soDo && <span className="ltag">{soDo}</span>}
            {noiThat && <span className="ltag">{noiThat}</span>}
          </div>
        )}
      </div>
    </Link>
  );
}
