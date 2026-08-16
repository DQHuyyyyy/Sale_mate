/**
 * Dựng câu trả lời của trợ lý — hỗ trợ đúng phần Markdown mà prompt cho phép:
 * gạch đầu dòng, `**in đậm**`, bảng so sánh, và trích nguồn `[Mã căn]`.
 *
 * CỐ Ý KHÔNG dùng `dangerouslySetInnerHTML`. Nội dung này do model sinh ra và
 * model có thể nhắc lại nguyên văn thứ người dùng gõ, nên nhét thẳng vào HTML
 * là mở đường cho script lạ. Dựng thành phần tử React thì trình duyệt tự escape,
 * an toàn theo cấu trúc chứ không nhờ lọc chuỗi.
 *
 * Cũng không kéo thêm thư viện markdown: prompt chỉ cho phép vài loại định dạng,
 * một trình dựng đầy đủ là thừa và thêm phụ thuộc phải bảo trì.
 */

// Trích nguồn model phát ra dạng [VOP781] hoặc [Chính sách bán hàng]. Giữ dấu
// ngoặc vuông trong prompt vì nó là dấu MÁY đọc được; đổi cách hiện là việc của
// tầng giao diện, không phải bắt model đổi cách viết.
const TRICH_DAN = /\[([^\]\n]{2,60})\]/g;

// Nhiều dấu đứng liền nhau — "[VOP345], [VOP247]" hay "[A] và [B]" — gỡ CẢ CHÙM
// một lượt, kể cả dấu phẩy/chữ "và" nối giữa. Gỡ từng dấu một thì phần nối ở
// giữa còn lại thành ", ." lửng lơ giữa câu.
const CHUOI_TRICH = /\[[^\]\n]{2,60}\](?:[ \t]*(?:,|;|và)?[ \t]*\[[^\]\n]{2,60}\])*/g;

/**
 * Gỡ mọi dấu trích nguồn khỏi thân bài, trả về danh sách nguồn để in một lần
 * ở cuối.
 *
 * Model gắn dấu vào TỪNG khẳng định, nên một câu trả lời tra cứu căn hộ có tám
 * gạch đầu dòng là tám lần "Trích VOP397" — cùng một nguồn lặp lại tám lần,
 * lấn át chính nội dung. Giá trị của trích nguồn là người đọc kiểm chứng được,
 * và một dòng ở cuối làm được đúng việc đó.
 *
 * Danh sách giữ thứ tự xuất hiện và bỏ trùng.
 */
function gomNguon(text) {
  const ten = [];
  const than = String(text ?? '').replace(CHUOI_TRICH, (chuoi) => {
    for (const [, nguon] of chuoi.matchAll(TRICH_DAN)) {
      if (!ten.includes(nguon)) ten.push(nguon);
    }
    return '';
  });

  return { than: donDauCau(than), nguon: ten };
}

/**
 * Dọn dấu câu mồ côi sau khi gỡ trích nguồn.
 *
 * Model hay kết bằng "Thông tin chi tiết được trích dẫn từ nguồn: [VOP345],
 * [VOP247]." Gỡ hai dấu ngoặc xong còn trơ lại "...từ nguồn:,." — dấu chồng dấu,
 * trông như lỗi hiển thị.
 */
function donDauCau(text) {
  return (
    text
      // Dấu ngăn đứng ngay trước một dấu khác thì thừa: ":,." còn ".".
      .replace(/[:,;](?=\s*[.,;:])/g, '')
      .replace(/[ \t]{2,}/g, ' ')
      .replace(/[ \t]+([.,;:)])/g, '$1')
      // Dòng kết thúc bằng dấu ngăn treo lơ lửng ("Nguồn:") thì bỏ luôn dấu đó.
      .replace(/[ \t]*[:,;]+[ \t]*$/gm, '')
  );
}

/** Tách `**in đậm**` thành các phần tử, giữ nguyên phần còn lại. */
function dungInDam(text, khoa) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((doan, i) =>
      doan.startsWith('**') && doan.endsWith('**') && doan.length > 4 ? (
        <strong key={`${khoa}-b${i}`}>{doan.slice(2, -2)}</strong>
      ) : (
        doan
      ),
    );
}

// Trích nguồn là mã căn thì bấm được để mở đúng căn đó. Tên tài liệu ("Chính
// sách hỗ trợ lãi suất…") thì không — chưa có trang riêng cho tài liệu, làm nó
// trông bấm được mà bấm không ra gì còn tệ hơn để chữ thường.
const LA_MA_CAN = /^[A-Za-z]{2,4}\d{2,5}$/;

/** Một tên nguồn: nút bấm nếu là mã căn, chữ thường nếu không. */
function MotNguon({ ten, onChonCan }) {
  if (!onChonCan || !LA_MA_CAN.test(ten)) return `"${ten}"`;
  return (
    <button type="button" className="ctl-trich-nut" onClick={() => onChonCan(ten)}>
      &quot;{ten}&quot;
    </button>
  );
}

/** Dựng một đoạn chữ. Dấu trích nguồn đã được `gomNguon` gỡ từ trước. */
function dungChu(text, khoa) {
  return dungInDam(String(text), khoa);
}

/** Dòng nguồn duy nhất ở cuối câu trả lời. */
function DongNguon({ nguon, onChonCan }) {
  if (!nguon.length) return null;

  return (
    <p className="ctl-nguon">
      <span className="ctl-nguon-nhan">Nguồn:</span>{' '}
      {nguon.map((ten, i) => (
        <span key={ten}>
          {i > 0 && ', '}
          <MotNguon ten={ten} onChonCan={onChonCan} />
        </span>
      ))}
    </p>
  );
}

const boTieuDe = (dong) => dong.replace(/^#{1,6}\s*/, '');
const laDongBang = (dong) => dong.trim().startsWith('|');
/** Dòng ngăn cách của bảng markdown: | --- | --- | */
const laDongNgan = (dong) => /^\|[\s|:-]+\|$/.test(dong.trim());

const tachO = (dong) =>
  dong
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((o) => o.trim());

function DungBang({ dong, khoa }) {
  const hang = dong.filter((d) => !laDongNgan(d)).map(tachO);
  if (!hang.length) return null;
  const [dau, ...than] = hang;

  return (
    // Bọc trong khối cuộn ngang: khung chat hẹp, bảng ba cột dễ tràn ra ngoài.
    <div className="ctl-bang-boc" key={`bang-${khoa}`}>
      <table className="ctl-bang">
        <thead>
          <tr>
            {dau.map((o, i) => (
              <th key={i}>{dungChu(o, `${khoa}-h${i}`)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {than.map((r, i) => (
            <tr key={i}>
              {r.map((o, j) => (
                <td key={j}>{dungChu(o, `${khoa}-${i}-${j}`)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * @param nguonThat Nguồn backend gửi qua event `sources` — gom từ tool và truy
 *   hồi thật. Đứng SAU nguồn model tự viết trong bài vì model chỉ trích những
 *   thứ nó thực sự dùng, còn danh sách của backend là toàn bộ thứ đã tra.
 *   Nhưng nó là thứ DUY NHẤT còn lại khi model bỏ qua luật trích nguồn — đúng
 *   chuyện đang xảy ra trên production với gpt-4o-mini.
 */
export default function CauTraLoi({ text, onChonCan, nguonThat }) {
  const { than, nguon: nguonTrongBai } = gomNguon(text);
  const nguon = [...new Set([...nguonTrongBai, ...(nguonThat ?? [])])];
  const dong = than.split('\n');
  const phanTu = [];
  let danhSach = [];
  let bang = [];

  const xaDanhSach = (khoa) => {
    if (!danhSach.length) return;
    phanTu.push(
      <ul key={`ul-${khoa}`} className="ctl-ds">
        {danhSach.map((item, i) => (
          <li key={i}>{dungChu(item, `${khoa}-${i}`)}</li>
        ))}
      </ul>,
    );
    danhSach = [];
  };

  const xaBang = (khoa) => {
    if (!bang.length) return;
    phanTu.push(<DungBang dong={bang} khoa={khoa} key={`b-${khoa}`} />);
    bang = [];
  };

  dong.forEach((raw, i) => {
    if (laDongBang(raw)) {
      xaDanhSach(i);
      bang.push(raw);
      return;
    }
    xaBang(i);

    const line = boTieuDe(raw.trim());
    const gach = line.match(/^[-*•]\s+(.*)$/);
    if (gach) {
      danhSach.push(gach[1]);
      return;
    }

    xaDanhSach(i);
    if (line) phanTu.push(<p key={`p-${i}`}>{dungChu(line, i)}</p>);
  });

  xaDanhSach('cuoi');
  xaBang('cuoi');

  return (
    <>
      {phanTu}
      <DongNguon nguon={nguon} onChonCan={onChonCan} />
    </>
  );
}
