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

const laMaCan = (nguon) => LA_MA_CAN.test(String(nguon.title ?? '').trim());

/**
 * Nguồn này là TÀI LIỆU hay là DỮ LIỆU tra cứu?
 *
 * Không chia theo `kind`. `kind` nói nguồn ĐẾN TỪ đâu (`db` = tool đã dùng thật,
 * `doc` = truy hồi lấy về), còn người đọc dòng nguồn cần biết nó TRỎ VÀO đâu:
 * một căn hộ cụ thể hay một văn bản chính sách. Hai câu hỏi khác nhau, và tool
 * `tinh_khoan_vay` là ca chứng minh — nó trả `kind="db"` (tool thật sự đã dùng)
 * nhưng nhãn là tên tài liệu chính sách và `doc_id` là `knowledge:…`, mở ra
 * được trang toàn văn. Xếp nó vào dòng "dữ liệu căn hộ" là nói sai bản chất.
 *
 * Nên tiền tố `doc_id` mới là thứ quyết, đúng luật đã dùng để quyết bấm được
 * hay không ở `MotNguon`.
 */
const laTaiLieu = (nguon) =>
  nguon.kind === 'doc' || String(nguon.doc_id ?? '').startsWith('knowledge:');

/**
 * Một nguồn — bấm được cho cả hai loại.
 *
 * Mã căn mở đúng căn đó; tên tài liệu mở `/tai-lieu/{doc_id}` xem toàn văn.
 * Trước đây tên tài liệu để chữ thường vì chưa có trang nào để mở, nên trích
 * nguồn chỉ là lời hứa: người đọc phải tin mà không kiểm được.
 *
 * Dấu ngoặc kép chỉ bọc TÊN TÀI LIỆU, không bọc mã căn: tên tài liệu dài và
 * nhiều chữ nên cần ranh giới khi liệt kê nhiều cái cách nhau bằng dấu phẩy,
 * còn "VOP841" thì tự nó đã là một khối.
 */
function MotNguon({ nguon, onChonCan }) {
  const ten = String(nguon.title ?? '').trim();
  if (laMaCan(nguon) && onChonCan) {
    return (
      <button type="button" className="ctl-trich-nut" onClick={() => onChonCan(ten)}>
        {ten}
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
  return laMaCan(nguon) ? ten : `"${ten}"`;
}

/**
 * Giờ đọc dữ liệu, dạng `08:32 08/09/2026`.
 *
 * Nói "đọc lúc" chứ KHÔNG nói "cập nhật lúc": mốc này là lúc trợ lý truy vấn
 * Postgres, không phải lúc ai đó sửa giá. Hai thứ khác nhau, và hệ thống chỉ
 * biết cái thứ nhất — viết thành "cập nhật" là khẳng định một điều không kiểm
 * được, đúng thứ nguyên tắc "không bịa số" cấm.
 */
function dinhDangLuc(luc) {
  const thoi_diem = new Date(luc);
  if (Number.isNaN(thoi_diem.getTime())) return '';
  const hai = (so) => String(so).padStart(2, '0');
  return (
    `${hai(thoi_diem.getHours())}:${hai(thoi_diem.getMinutes())} ` +
    `${hai(thoi_diem.getDate())}/${hai(thoi_diem.getMonth() + 1)}/${thoi_diem.getFullYear()}`
  );
}

/** Liệt kê các nguồn, ngăn bằng dấu phẩy. */
function LietKe({ nguon, onChonCan, tuChiSo = 0 }) {
  return nguon.map((n, i) => (
    <span key={n.doc_id ? `${n.doc_id}-${n.title}` : n.title}>
      {i + tuChiSo > 0 && ', '}
      <MotNguon nguon={n} onChonCan={onChonCan} />
    </span>
  ));
}

/** Dựng một đoạn chữ. Dấu trích nguồn đã được `gomNguon` gỡ từ trước. */
function dungChu(text, khoa) {
  return dungInDam(String(text), khoa);
}

/**
 * Khối nguồn ở cuối câu trả lời — TÁCH THEO LOẠI, không gộp một dòng.
 *
 * Nhãn cũ là "Nguồn:" rồi liệt kê thẳng `"VOP841", "VOP619"`. Đợt test
 * 08/09/2026 cho thấy sale không hiểu dãy mã trần đó là gì — có người tưởng
 * là lỗi hiển thị hoặc log debug sót lại. "Dữ liệu tham chiếu" nói rõ đây là
 * thứ trợ lý đã tra để trả lời, không phải một phần của câu trả lời.
 *
 * Tách hai dòng vì hai loại nguồn trả lời hai câu hỏi khác nhau, và gộp chúng
 * lại từng gây hiểu nhầm thật: lượt hỏi căn VOP9999 liệt kê chung một dòng cả
 * "Chính sách hỗ trợ lãi suất chung" lẫn "Tổng quan Ocean Park 1/3", và người
 * đọc tưởng ba tài liệu đó nói về căn VOP9999.
 *
 * Mốc thời gian chỉ gắn cho dòng DỮ LIỆU. Giá và tình trạng căn đọc thẳng từ
 * Postgres lúc hỏi nên mốc đó có nghĩa; tài liệu thì là bản chụp trong vector
 * store và hệ thống không biết nó được nạp lúc nào — gắn một con giờ vào đấy là
 * hứa một điều không kiểm được.
 */
function DongNguon({ nguon, onChonCan, luc }) {
  if (!nguon.length) return null;

  const taiLieu = nguon.filter(laTaiLieu);
  const duLieu = nguon.filter((n) => !laTaiLieu(n));
  // Mã căn đứng trước nhãn tổng hợp ("Dữ liệu tồn kho") để chữ "căn" nói đúng
  // về phần ngay sau nó.
  const maCan = duLieu.filter(laMaCan);
  const tongHop = duLieu.filter((n) => !laMaCan(n));

  return (
    <div className="ctl-nguon">
      {duLieu.length > 0 && (
        <p className="ctl-nguon-dong">
          <span className="ctl-nguon-nhan">
            <span aria-hidden="true">📄</span> Dữ liệu tham chiếu:
          </span>{' '}
          {maCan.length > 0 && 'căn '}
          <LietKe nguon={maCan} onChonCan={onChonCan} />
          <LietKe nguon={tongHop} onChonCan={onChonCan} tuChiSo={maCan.length} />
          {luc && <span className="ctl-nguon-luc"> · đọc lúc {dinhDangLuc(luc)}</span>}
        </p>
      )}

      {taiLieu.length > 0 && (
        <p className="ctl-nguon-dong">
          <span className="ctl-nguon-nhan">
            <span aria-hidden="true">📄</span> Theo tài liệu:
          </span>{' '}
          <LietKe nguon={taiLieu} onChonCan={onChonCan} />
        </p>
      )}
    </div>
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
 * @param nguonLuc Mốc thời gian (ms) lúc widget nhận được event `sources`, tức
 *   lúc trợ lý vừa đọc xong dữ liệu. Không có thì dòng dữ liệu không hiện giờ —
 *   thà thiếu còn hơn hiện một mốc không biết từ đâu ra.
 */
export default function CauTraLoi({ text, onChonCan, nguonThat, choTrichNguon, nguonLuc }) {
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
      <DongNguon nguon={nguon} onChonCan={onChonCan} luc={nguonLuc} />
    </>
  );
}
