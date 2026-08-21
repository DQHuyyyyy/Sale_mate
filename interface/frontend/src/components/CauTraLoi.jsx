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

import { Link } from 'react-router-dom';

// Trích nguồn model phát ra dạng [VOP781] hoặc [Chính sách bán hàng]. Giữ dấu
// ngoặc vuông trong prompt vì nó là dấu MÁY đọc được; đổi cách hiện là việc của
// tầng giao diện, không phải bắt model đổi cách viết.
const TRICH_DAN = /\[([^\]\n]{2,60})\]/g;

// Nhiều dấu đứng liền nhau — "[VOP345], [VOP247]" hay "[A] và [B]" — gỡ CẢ CHÙM
// một lượt, kể cả dấu phẩy/chữ "và" nối giữa. Gỡ từng dấu một thì phần nối ở
// giữa còn lại thành ", ." lửng lơ giữa câu.
const CHUOI_TRICH = /\[[^\]\n]{2,60}\](?:[ \t]*(?:,|;|và)?[ \t]*\[[^\]\n]{2,60}\])*/g;

// Chỗ điền trong prompt, không phải tên nguồn nào. Prompt dạy cách trích dẫn
// bằng ví dụ `[Mã căn]` và `[Tên tài liệu]`; model yếu chép luôn cái ví dụ thay
// vì thay bằng giá trị thật, rồi FE dựng nó thành một nguồn bấm được. Đã thấy
// `Nguồn: "Tên tài liệu"` hiện ra trước mặt người dùng trên production.
const CHO_DIEN = new Set([
  'mã căn',
  'tên tài liệu',
  'ma can',
  'ten tai lieu',
  'thông tin cụ thể còn thiếu',
  'tên nguồn',
  'nguồn',
  // Tên TOOL, không phải tên nguồn. Câu trả lời tổng hợp ("còn 30 căn") không
  // có mã căn lẫn tên tài liệu nào, nên model hay lấy định danh duy nhất nó
  // nhìn thấy trong ngữ cảnh — tên tool — làm nguồn. Backend đã cấp nhãn đúng
  // ("Dữ liệu tồn kho"); đây là lưới chặn khi model vẫn chép tên máy.
  'inventory_lookup',
  'inventory_search',
  'inventory_summary',
  'so_sanh_can',
  'tinh_khoan_vay',
  'dat_coc',
]);

const laChoDien = (ten) => CHO_DIEN.has(ten.trim().toLowerCase());

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
      // Vẫn gỡ khỏi thân bài, chỉ không tính là nguồn.
      if (!laChoDien(nguon) && !ten.includes(nguon)) ten.push(nguon);
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

const LA_MA_CAN = /^[A-Za-z]{2,4}\d{2,5}$/;

/**
 * Một nguồn — bấm được cho cả hai loại.
 *
 * Mã căn mở đúng căn đó; tên tài liệu mở `/tai-lieu/{doc_id}` xem toàn văn.
 * Trước đây tên tài liệu để chữ thường vì chưa có trang nào để mở, nên trích
 * nguồn chỉ là lời hứa: người đọc phải tin mà không kiểm được.
 */
function MotNguon({ nguon, onChonCan }) {
  const ten = nguon.title;
  if (LA_MA_CAN.test(ten) && onChonCan) {
    return (
      <button type="button" className="ctl-trich-nut" onClick={() => onChonCan(ten)}>
        &quot;{ten}&quot;
      </button>
    );
  }
  // Bấm được hay không do TIỀN TỐ `doc_id` quyết, KHÔNG do `kind`. `kind` nói
  // nguồn đến từ đâu (tool hay truy hồi); tiền tố nói nó trỏ vào đâu. Tool
  // `tinh_khoan_vay` đọc số từ tài liệu chính sách nên `kind="db"` mà `doc_id`
  // vẫn là `knowledge:…` — mở được. Còn "Dữ liệu tồn kho" (`inventory:postgres`)
  // thì không có trang nào để mở.
  if (String(nguon.doc_id ?? '').startsWith('knowledge:')) {
    return (
      <Link className="ctl-trich-nut" to={`/tai-lieu/${encodeURIComponent(nguon.doc_id)}`}>
        &quot;{ten}&quot;
      </Link>
    );
  }
  return `"${ten}"`;
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
      {nguon.map((n, i) => (
        <span key={n.doc_id ? `${n.doc_id}-${n.title}` : n.title}>
          {i > 0 && ', '}
          <MotNguon nguon={n} onChonCan={onChonCan} />
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
 * @param choTrichNguon Backend đã lọc và kết luận lượt này KHÔNG được trích
 *   nguồn (hỏi ngược, từ chối, chưa khẳng định gì). Chỉ `false` mới chặn —
 *   `undefined` nghĩa là chưa có event `done`, giữ nguyên hành vi cũ để một
 *   lượt stream đứt giữa chừng không mất sạch nguồn.
 */
export default function CauTraLoi({ text, onChonCan, nguonThat, choTrichNguon }) {
  // `gomNguon` vẫn chạy để GỠ dấu trích khỏi thân bài — "[VOP758]" giữa câu là
  // cú pháp nội bộ, người đọc không cần thấy. Nhưng TÊN nó rút ra thì bỏ đi.
  const { than } = gomNguon(text);

  // Chỉ hiện nguồn BACKEND duyệt. Tên model tự viết trong ngoặc vuông không
  // được tính nữa: model đọc mục "Nguồn tham khảo" ở cuối tài liệu, thấy
  // "[Sang tên Sổ đỏ 2026 — LuatVietnam](https://…)" — trùng đúng cú pháp trích
  // dẫn — rồi chép làm nhãn nguồn. Dòng "Nguồn" hoá ra trỏ sang một bài báo
  // ngoài, trong khi thứ trợ lý thật sự đọc là tài liệu nội bộ. Người đọc tưởng
  // trợ lý vừa tra web thời gian thực; nó không hề, và không có tool nào làm
  // được việc đó.
  //
  // Nguồn của backend có `doc_id` nên bấm vào mở được tài liệu — thứ tên model
  // tự nghĩ ra không bao giờ có.
  const nguon = choTrichNguon === false ? [] : (nguonThat ?? []);
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
