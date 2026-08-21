import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DU_AN_SO_DO, duongDanSoDo, timDuAn } from '../utils/soDoPhanKhu';

// Chừa lề quanh khu sau khi phóng: lấp đầy khung 100% thì khu dính sát mép và
// mất hết ngữ cảnh xung quanh — người xem không còn biết nó nằm ở đâu trong khu đô thị.
const HE_SO_LE = 0.82;

// Ảnh nền rộng 4096px, khung xem thường rộng ~1100px. Quá 5 lần là bắt đầu thấy
// điểm ảnh, phóng thêm chỉ để nhìn ảnh vỡ.
const TY_LE_TOI_DA = 5;

const TOAN_CANH = { k: 1, x: 0, y: 0 };

/**
 * Đổi hộp bao của một khu thành phép biến hình cho cả tấm bản đồ.
 *
 * Tính bằng TỈ LỆ (0–1) chứ không bằng pixel, nên đổi kích thước cửa sổ hay xem
 * trên điện thoại đều không phải tính lại: khung xem co giãn thì ảnh co giãn theo.
 */
function tinhKhungNhin(bbox, khung) {
  const fx = bbox.x / khung.rong;
  const fy = bbox.y / khung.cao;
  const fw = bbox.width / khung.rong;
  const fh = bbox.height / khung.cao;

  const k = Math.min(Math.max(Math.min(1 / fw, 1 / fh) * HE_SO_LE, 1), TY_LE_TOI_DA);

  // Kéo tâm khu về giữa khung xem. Kẹp lại trong [1-k, 0] để không bao giờ lộ
  // khoảng trắng ở mép — phóng vào một khu sát rìa bản đồ là ca hay quên nhất.
  const gioiHan = (gia_tri) => Math.min(0, Math.max(1 - k, gia_tri));

  return {
    k,
    x: gioiHan(0.5 - k * (fx + fw / 2)),
    y: gioiHan(0.5 - k * (fy + fh / 2)),
  };
}

/**
 * Phóng quanh MỘT ĐIỂM, giữ nguyên thứ nằm dưới điểm đó.
 *
 * `diem` là toạ độ con trỏ tính theo tỉ lệ khung xem (0–1). Phóng quanh tâm khung
 * thay vì quanh con trỏ thì chỗ người ta đang nhắm trôi đi mất sau mỗi nấc lăn,
 * và họ phải rượt theo nó.
 */
function phongTaiDiem(truoc, diem, heSo) {
  const k = Math.min(Math.max(truoc.k * heSo, 1), TY_LE_TOI_DA);
  // Toạ độ của điểm đó trên chính tấm bản đồ — bất biến qua phép phóng.
  const px = (diem.x - truoc.x) / truoc.k;
  const py = (diem.y - truoc.y) / truoc.k;
  const gioiHan = (gia_tri) => Math.min(0, Math.max(1 - k, gia_tri));
  return { k, x: gioiHan(diem.x - k * px), y: gioiHan(diem.y - k * py) };
}

// Một nấc lăn chuột ~100px đổi ra ~1,16 lần. Nhân theo hàm mũ chứ không cộng
// thêm một lượng cố định: cộng thì lúc đang phóng sâu mỗi nấc nhảy một quãng
// khác hẳn lúc đang xem toàn cảnh.
const DO_NHAY_LAN = 0.0015;

export default function SoDoPhanKhu() {
  const { duAn: maDuAn } = useParams();
  const duAn = timDuAn(maDuAn);

  const [dangChon, setDangChon] = useState(null);
  const [dangTro, setDangTro] = useState(null);
  const [khungNhin, setKhungNhin] = useState(TOAN_CANH);
  // Bấm vào khu thì chạy chuyển động cho mượt; lăn chuột thì TẮT, vì mỗi nấc lăn
  // lại hẹn một chuyển động 0,45s mới và cả dãy nấc dồn thành một cú trượt dây thun.
  const [muot, setMuot] = useState(true);
  const oKhung = useRef(null);
  // Bộ nghe lăn chuột gắn một lần, nên nó không thấy state mới nếu đọc trực tiếp.
  const khungNhinHienTai = useRef(TOAN_CANH);
  // Hộp bao chỉ đọc được từ DOM (`getBBox`), nên giữ tham chiếu tới từng path.
  // Nhờ vậy bấm trên bản đồ và bấm ở danh sách bên dưới chạy chung một hàm.
  const oVung = useRef({});

  useEffect(() => {
    khungNhinHienTai.current = khungNhin;
  }, [khungNhin]);

  const veToanCanh = useCallback(() => {
    setMuot(true);
    setDangChon(null);
    setKhungNhin(TOAN_CANH);
  }, []);

  // Đổi dự án mà giữ nguyên khung nhìn cũ thì trang mới mở ra đang phóng vào một
  // toạ độ của bản đồ khác.
  useEffect(() => {
    veToanCanh();
    setDangTro(null);
  }, [maDuAn, veToanCanh]);

  useEffect(() => {
    const nghe = (su_kien) => {
      if (su_kien.key === 'Escape') veToanCanh();
    };
    document.addEventListener('keydown', nghe);
    return () => document.removeEventListener('keydown', nghe);
  }, [veToanCanh]);

  // Gắn TAY chứ không dùng `onWheel` của React: React đăng ký wheel ở chế độ
  // passive, nên `preventDefault()` trong đó không có tác dụng và trang vẫn cuộn
  // trong lúc người dùng phóng bản đồ.
  useEffect(() => {
    const khung = oKhung.current;
    if (!khung) return undefined;

    const lan = (su_kien) => {
      // Firefox trả delta theo DÒNG (deltaMode 1), Chrome theo pixel. Không quy
      // về cùng đơn vị thì cùng một nấc lăn cho hai tốc độ phóng khác hẳn nhau.
      const buoc = su_kien.deltaMode === 1 ? su_kien.deltaY * 16 : su_kien.deltaY;
      const truoc = khungNhinHienTai.current;
      const hop = khung.getBoundingClientRect();
      const moi = phongTaiDiem(
        truoc,
        { x: (su_kien.clientX - hop.left) / hop.width, y: (su_kien.clientY - hop.top) / hop.height },
        Math.exp(-buoc * DO_NHAY_LAN),
      );

      // Đã chạm trần hoặc đang ở toàn cảnh mà còn lăn ra: nhường lại cho trang
      // cuộn như thường. Nuốt sự kiện ở đây là bản đồ khoá trang mà không làm gì.
      if (moi.k === truoc.k && moi.x === truoc.x && moi.y === truoc.y) return;

      su_kien.preventDefault();
      setMuot(false);
      setKhungNhin(moi);
      // Lăn về đúng toàn cảnh thì bỏ luôn khu đang chọn — giữ lại thì cái nhãn
      // tên khu vẫn nằm đó trong khi khung nhìn đã không còn khoanh vào nó.
      if (moi.k === 1) setDangChon(null);
    };

    khung.addEventListener('wheel', lan, { passive: false });
    return () => khung.removeEventListener('wheel', lan);
  }, [maDuAn]);

  const phongTo = (ma) => {
    // Bấm lại đúng khu đang xem là muốn thoát ra — không bắt đi tìm nút riêng.
    if (ma === dangChon) {
      veToanCanh();
      return;
    }
    const path = oVung.current[ma];
    if (!path) return;
    setMuot(true);
    setDangChon(ma);
    setKhungNhin(tinhKhungNhin(path.getBBox(), duAn.khung));
  };

  if (!duAn) {
    return (
      <div className="wrap">
        <div className="page-head">
          <h1>Không có sơ đồ này</h1>
          <p>Đường dẫn không trỏ tới dự án nào trong Ocean City.</p>
        </div>
        <Link className="btn btn-primary" to={duongDanSoDo('op1')}>
          Xem sơ đồ Ocean Park 1
        </Link>
      </div>
    );
  }

  // Rê chuột lên khu khác thì xem trước tên khu ĐÓ, kể cả khi đang chọn sẵn một
  // khu — người dùng rê là đang hỏi "khu này tên gì", trả lời tên khu cũ là trả
  // lời câu họ không hỏi. Bỏ tay ra thì quay về khu đang chọn.
  const vungDangHien = duAn.vung.find((vung) => vung.ma === (dangTro ?? dangChon));

  return (
    <div className="wrap sdo-trang">
      <div className="page-head">
        <h1>Sơ đồ phân khu {duAn.ten}</h1>
      </div>

      <div className="sdo-tabs">
        {DU_AN_SO_DO.map((muc) => (
          <Link
            key={muc.ma}
            to={duongDanSoDo(muc.ma)}
            className={muc.ma === duAn.ma ? 'sdo-tab on' : 'sdo-tab'}
          >
            {muc.ten}
          </Link>
        ))}
      </div>

      {duAn.vung.length ? (
        <>
          {/* Bấm vào nền (không trúng khu nào) là thu về toàn cảnh. Cùng cử chỉ
              với Esc, chỉ khác đường vào. */}
          {/* Tỉ lệ khung đi theo TỪNG dự án: OP1 và OP2 nằm ngang, OP3 nằm dọc.
              Viết cứng một tỉ lệ vào CSS là ảnh dự án thứ ba bị bóp méo. */}
          <div
            className="sdo-khung"
            ref={oKhung}
            onClick={veToanCanh}
            style={{
              '--ti-le': `${duAn.khung.rong} / ${duAn.khung.cao}`,
              '--ti-le-so': duAn.khung.rong / duAn.khung.cao,
            }}
          >
            <div
              className="sdo-canvas"
              style={{
                transform: `translate(${khungNhin.x * 100}%, ${khungNhin.y * 100}%) scale(${khungNhin.k})`,
                transition: muot ? undefined : 'none',
              }}
            >
              <img
                src={duAn.anh}
                alt={`Sơ đồ phân khu ${duAn.ten}`}
                width={duAn.khung.rong}
                height={duAn.khung.cao}
                draggable={false}
              />
              {/* `preserveAspectRatio="none"` để lớp phủ giãn ĐÚNG bằng khung, y
                  như ảnh nền bên dưới (object-fit: fill). Nếu một bên co theo tỉ
                  lệ còn bên kia lấp đầy, chỉ cần khung lệch nửa pixel do làm tròn
                  là vùng bấm trượt khỏi khu nó khoanh. */}
              <svg
                className="sdo-lop"
                viewBox={`0 0 ${duAn.khung.rong} ${duAn.khung.cao}`}
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                {duAn.vung.map((vung) => (
                  <path
                    key={vung.ma}
                    ref={(path) => {
                      oVung.current[vung.ma] = path;
                    }}
                    d={vung.d}
                    className={vung.ma === dangChon ? 'sdo-vung on' : 'sdo-vung'}
                    onClick={(su_kien) => {
                      su_kien.stopPropagation();
                      phongTo(vung.ma);
                    }}
                    onMouseEnter={() => setDangTro(vung.ma)}
                    onMouseLeave={() => setDangTro(null)}
                  >
                    <title>{vung.ten}</title>
                  </path>
                ))}
              </svg>
            </div>

            {/* `key` đổi theo khu nên React dựng lại thẻ này mỗi lần đổi khu, và
                animation chạy lại từ đầu. Không có nó thì chỉ chữ đổi, nhãn đứng
                im — chuyển động chỉ thấy đúng một lần đầu tiên. */}
            {vungDangHien && (
              <div
                key={vungDangHien.ma}
                className={vungDangHien.ma === dangChon ? 'sdo-nhan on' : 'sdo-nhan'}
              >
                <span className="sdo-cham" />
                {vungDangHien.ten}
              </div>
            )}

            {khungNhin.k > 1 && (
              <button
                type="button"
                className="btn-nho sdo-thu-nho"
                onClick={(su_kien) => {
                  su_kien.stopPropagation();
                  veToanCanh();
                }}
              >
                Xem toàn cảnh
              </button>
            )}
          </div>

          {/* Danh sách này không chỉ để trang trí: vùng bấm trên SVG không đến
              được bằng bàn phím, và tên khu chỉ hiện khi rê chuột. Đây là lối
              vào thứ hai, dùng được cho cả hai việc. */}
          <div className="sdo-ds">
            {duAn.vung.map((vung) => (
              <button
                key={vung.ma}
                type="button"
                className={vung.ma === dangChon ? 'btn-nho on' : 'btn-nho'}
                onClick={() => phongTo(vung.ma)}
                onMouseEnter={() => setDangTro(vung.ma)}
                onMouseLeave={() => setDangTro(null)}
              >
                {vung.ten}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="empty">
          Sơ đồ tương tác của {duAn.ten} chưa có. Hiện mới có{' '}
          <Link to={duongDanSoDo('op1')}>Vinhomes Ocean Park 1</Link>.
        </div>
      )}
    </div>
  );
}
