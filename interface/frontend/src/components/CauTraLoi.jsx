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

/** Gộp các trích nguồn đứng liền nhau thành một: Trích "A", "B". */
function tachTrichDan(text) {
  const phan = [];
  let vitri = 0;
  let dangGom = null;

  const xa = () => {
    if (dangGom) {
      phan.push({ trich: dangGom });
      dangGom = null;
    }
  };

  for (const khop of text.matchAll(TRICH_DAN)) {
    const truoc = text.slice(vitri, khop.index);
    // Chỉ khoảng trắng giữa hai trích dẫn thì gom chung, không lặp chữ "Trích".
    if (truoc.trim() === '' && dangGom) {
      dangGom.push(khop[1]);
    } else {
      xa();
      if (truoc) phan.push({ chu: truoc });
      dangGom = [khop[1]];
    }
    vitri = khop.index + khop[0].length;
  }

  xa();
  const con_lai = text.slice(vitri);
  if (con_lai) phan.push({ chu: con_lai });
  return phan;
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

/** Dựng một đoạn chữ: in đậm + trích nguồn. */
function dungChu(text, khoa) {
  return tachTrichDan(String(text)).map((phan, i) =>
    phan.trich ? (
      <em key={`${khoa}-t${i}`} className="ctl-trich">
        Trích {phan.trich.map((ten) => `"${ten}"`).join(', ')}
      </em>
    ) : (
      <span key={`${khoa}-c${i}`}>{dungInDam(phan.chu, `${khoa}-${i}`)}</span>
    ),
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

export default function CauTraLoi({ text }) {
  const dong = String(text ?? '').split('\n');
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
  return <>{phanTu}</>;
}
