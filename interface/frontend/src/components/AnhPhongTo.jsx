import { useEffect } from 'react';
import { CloseIcon } from './Icons';

/**
 * Xem một ảnh ở kích thước lớn, phủ toàn màn hình.
 *
 * Sinh ra cho ảnh AI trong khung chat: sidebar rộng 33vw nên ảnh hiện ở đó chỉ
 * vài trăm pixel — khách vừa yêu cầu "xoá bộ bàn ghế ở góc tường" thì không soi
 * nổi kết quả để biết model có làm đúng không.
 *
 * Tách thành component riêng thay vì viết thẳng trong `ChatSidebar`: gallery ở
 * trang chi tiết căn cũng cần đúng thứ này, và hai bản chép tay sẽ lệch nhau ở
 * đúng những chỗ khó thấy (phím Esc, khoá cuộn nền).
 */
export default function AnhPhongTo({ src, alt, ghiChu, onDong }) {
  useEffect(() => {
    const theoPhim = (e) => {
      if (e.key === 'Escape') onDong();
    };
    document.addEventListener('keydown', theoPhim);

    // Khoá cuộn trang nền: không khoá thì lăn chuột trên ảnh làm trang phía sau
    // trôi đi, đóng ảnh ra là lạc mất chỗ đang đọc.
    const cuonCu = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', theoPhim);
      document.body.style.overflow = cuonCu;
    };
  }, [onDong]);

  return (
    // Bấm nền để đóng là thói quen ai cũng có. `stopPropagation` trên khung ảnh
    // để bấm vào chính tấm ảnh thì không đóng nhầm.
    <div className="anh-to" role="dialog" aria-modal="true" aria-label={alt} onClick={onDong}>
      <button className="anh-to-dong" aria-label="Đóng" onClick={onDong}>
        <CloseIcon />
      </button>
      <figure className="anh-to-khung" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} />
        {ghiChu && <figcaption>{ghiChu}</figcaption>}
      </figure>
    </div>
  );
}
