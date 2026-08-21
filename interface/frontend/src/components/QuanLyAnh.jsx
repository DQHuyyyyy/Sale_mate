import { useRef, useState } from 'react';
import { datAnhDaiDien, uploadApartmentImages, xoaAnhCanHo } from '../api';

/**
 * Bảng quản lý ảnh của một căn — chỉ admin thấy.
 *
 * Đặt ngay dưới gallery chứ không nằm trong một trang quản trị riêng: lúc quyết
 * định ảnh nào lên bìa, người ta cần nhìn thấy đủ cả 4 ảnh ở kích thước thật.
 *
 * Thao tác trên ẢNH ĐANG XEM, không phải trên từng thumbnail. Nhờ vậy nút vẫn
 * dùng được khi căn chỉ có một ảnh (lúc đó dãy thumbnail bị ẩn), và khi căn
 * chưa có ảnh nào thì nút "Thêm ảnh" vẫn đứng đó.
 */
export default function QuanLyAnh({ maCan, images, chiSoAnh, onCapNhat }) {
  const [dangChay, setDangChay] = useState(false);
  const [loi, setLoi] = useState('');
  const inputRef = useRef(null);

  const anhHienTai = images[chiSoAnh];
  const laAnhDaiDien = images.length > 0 && chiSoAnh === 0;

  // `chiSoSauKhiXong` là ảnh muốn xem tiếp sau khi thao tác xong: mặc định về
  // ảnh đầu (ảnh sắp lên thẻ tìm kiếm), riêng lúc upload thì nhảy tới ảnh vừa
  // thêm để bấm "Đặt làm ảnh đại diện" ngay, không phải đi tìm nó ở cuối dãy.
  const chay = async (viec, chiSoSauKhiXong = 0) => {
    setDangChay(true);
    setLoi('');
    try {
      onCapNhat(await viec(), chiSoSauKhiXong);
    } catch (thaoTacError) {
      setLoi(thaoTacError.message);
    } finally {
      setDangChay(false);
    }
  };

  const xoaAnh = () => {
    const ok = window.confirm(
      `Xoá ảnh ${chiSoAnh + 1} của căn ${maCan}?\n\n` +
        'Ảnh sẽ biến mất khỏi trang tìm kiếm, trang căn hộ và widget trợ lý. ' +
        'Không hoàn tác được.',
    );
    if (ok) chay(() => xoaAnhCanHo(maCan, anhHienTai.id));
  };

  const themAnh = (event) => {
    const files = event.target.files;
    if (!files?.length) return;
    // Xoá value sau khi xong: không có bước này thì chọn lại đúng file vừa
    // upload sẽ không kích hoạt onChange, người dùng tưởng nút hỏng.
    chay(() => uploadApartmentImages(maCan, files), images.length).finally(() => {
      if (inputRef.current) inputRef.current.value = '';
    });
  };

  return (
    <div className="quan-ly-anh">
      <div className="qla-hang">
        <button
          className="btn-nho"
          disabled={!anhHienTai || laAnhDaiDien || dangChay}
          onClick={() => chay(() => datAnhDaiDien(maCan, anhHienTai.id))}
        >
          {laAnhDaiDien ? 'Đang là ảnh đại diện' : 'Đặt làm ảnh đại diện'}
        </button>
        <button className="btn-nho" disabled={!anhHienTai || dangChay} onClick={xoaAnh}>
          Xoá ảnh này
        </button>
        <label className="btn-nho qla-them">
          Thêm ảnh
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            multiple
            hidden
            disabled={dangChay}
            onChange={themAnh}
          />
        </label>
      </div>
      <p className="hint">
        Ảnh đầu tiên là ảnh hiện trên thẻ ở trang tìm kiếm. Bấm vào một ảnh nhỏ rồi đặt làm ảnh
        đại diện để đổi.
      </p>
      {loi && <div className="alert alert-error">{loi}</div>}
    </div>
  );
}
