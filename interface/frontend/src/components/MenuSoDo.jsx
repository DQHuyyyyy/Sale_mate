import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { DU_AN_SO_DO, duongDanSoDo } from '../utils/soDoPhanKhu';

/**
 * Bọc một nút bất kỳ thành menu thả xuống ba dự án Ocean Park.
 *
 * Mở bằng DI CHUỘT và cả bằng BẤM. Chỉ hover thì màn cảm ứng không có cách nào
 * vào — điện thoại không có trạng thái "đang trỏ vào", chạm một cái là trình
 * duyệt hiểu thành click.
 *
 * Vùng bắt chuột là cả khối bọc chứ không riêng cái nút, nếu không thì khoảng
 * hở giữa nút và menu làm menu đóng ngay lúc người dùng đang rê xuống nó.
 */
export default function MenuSoDo({ children, lopBoc = '', lopNut = '', khiChon }) {
  const [mo, setMo] = useState(false);
  const boc = useRef(null);

  useEffect(() => {
    if (!mo) return undefined;
    const nghe = (su_kien) => {
      if (su_kien.key === 'Escape') setMo(false);
    };
    document.addEventListener('keydown', nghe);
    return () => document.removeEventListener('keydown', nghe);
  }, [mo]);

  const dong = () => {
    setMo(false);
    khiChon?.();
  };

  return (
    <div
      ref={boc}
      className={`menu-so-do ${lopBoc}`.trim()}
      onMouseEnter={() => setMo(true)}
      onMouseLeave={() => setMo(false)}
      // Rời khối bằng phím Tab thì đóng — nhưng nhảy giữa các mục BÊN TRONG menu
      // cũng bắn ra sự kiện này, nên phải hỏi điểm đến còn nằm trong khối không.
      onBlur={(su_kien) => {
        if (!boc.current?.contains(su_kien.relatedTarget)) setMo(false);
      }}
    >
      <button
        type="button"
        className={lopNut}
        aria-haspopup="true"
        aria-expanded={mo}
        onClick={() => setMo((truoc) => !truoc)}
      >
        {children}
      </button>

      {mo && (
        <div className="msd-menu">
          {DU_AN_SO_DO.map((duAn) => (
            <Link key={duAn.ma} to={duongDanSoDo(duAn.ma)} onClick={dong}>
              {duAn.ten}
              {/* Nói trước khu nào chưa có sơ đồ, ngay trên menu: bấm vào rồi mới
                  biết là mất một lượt chuyển trang cho một trang trống. */}
              {!duAn.vung.length && <span className="msd-sap">Sắp có</span>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
