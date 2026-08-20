import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getTaiLieuAI, getTaiLieuAIChiTiet } from '../api';
import { BackIcon } from '../components/Icons';

/**
 * Kho tài liệu trợ lý dùng để trả lời — và đích của mọi nút trích nguồn.
 *
 * Trích nguồn chỉ có giá trị khi bấm vào xem được. Trước trang này, dòng
 * "Nguồn" là chữ chết: người đọc phải tin lời trợ lý mà không có cách đối chiếu.
 *
 * Khác trang `/documents`: chỗ đó là tài liệu admin tự đăng (link, PDF) trong
 * bảng `documents`. Đây là kho lõi AI THẬT SỰ đọc — hai thứ khác nhau, và gộp
 * lại thì không ai biết trợ lý đang trích từ đâu.
 */

/**
 * Dựng markdown ở mức tối thiểu: tiêu đề, gạch đầu dòng, in đậm, bảng bỏ qua.
 *
 * Không kéo thư viện markdown về chỉ để hiện 11 tài liệu — chúng do chính đội
 * mình soạn, cú pháp đã biết trước và hẹp. `CauTraLoi.jsx` cũng tự dựng vì cùng
 * lý do; thêm phụ thuộc ở đây là thêm một thứ phải cập nhật mãi.
 */
function dungMarkdown(text) {
  const phanTu = [];
  let danhSach = [];

  const xaDanhSach = (khoa) => {
    if (!danhSach.length) return;
    phanTu.push(
      <ul key={`ul-${khoa}`} className="tl-ds">
        {danhSach.map((item, i) => (
          <li key={i}>{dungInDam(item)}</li>
        ))}
      </ul>,
    );
    danhSach = [];
  };

  String(text ?? '')
    .split('\n')
    .forEach((dong, i) => {
      const sach = dong.trim();
      if (sach.startsWith('- ') || sach.startsWith('* ')) {
        danhSach.push(sach.slice(2));
        return;
      }
      xaDanhSach(i);
      if (!sach) return;
      const cap = sach.match(/^(#{1,4})\s+(.*)$/);
      if (cap) {
        const The = `h${Math.min(cap[1].length + 1, 5)}`;
        phanTu.push(<The key={i}>{dungInDam(cap[2])}</The>);
        return;
      }
      phanTu.push(<p key={i}>{dungInDam(sach)}</p>);
    });

  xaDanhSach('cuoi');
  return phanTu;
}

/** `**in đậm**` và `[chữ](link)` — hai thứ duy nhất xuất hiện trong tài liệu. */
function dungInDam(text) {
  return String(text)
    .split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g)
    .filter(Boolean)
    .map((doan, i) => {
      if (doan.startsWith('**') && doan.endsWith('**')) return <strong key={i}>{doan.slice(2, -2)}</strong>;
      const link = doan.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (link) {
        return (
          // Link ra ngoài: `noopener` bắt buộc, trang đích không được chạm
          // `window.opener` của mình.
          <a key={i} href={link[2]} target="_blank" rel="noopener noreferrer">
            {link[1]}
          </a>
        );
      }
      return doan;
    });
}

export function TaiLieuAIDanhSach() {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getTaiLieuAI()
      .then(setDocs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Tài liệu trợ lý</h1>
        <p>
          Đây là toàn bộ nguồn trợ lý dùng để trả lời. Trợ lý không đọc gì ngoài danh sách này —
          bấm vào một tài liệu để xem đúng nội dung nó đã dùng.
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="panel">
        <div className="sec-hd">
          <h2>{docs.length} tài liệu</h2>
        </div>

        {loading && <div className="loading">Đang tải danh sách…</div>}
        {!loading && docs.length === 0 && !error && <div className="empty">Chưa có tài liệu nào.</div>}

        {!loading && docs.length > 0 && (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Tài liệu</th>
                  <th>Nhóm</th>
                  <th>Phiên bản</th>
                  <th>Độ dài</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.doc_id}>
                    <td className="cell-strong">{d.title}</td>
                    <td>{d.section || '—'}</td>
                    <td className="mono">{d.version || '—'}</td>
                    <td>{d.so_ky_tu.toLocaleString('vi-VN')} ký tự</td>
                    <td>
                      <Link className="btn-nho" to={`/tai-lieu/${encodeURIComponent(d.doc_id)}`}>
                        Xem
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function TaiLieuAIChiTiet() {
  const { docId } = useParams();
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    getTaiLieuAIChiTiet(docId)
      .then(setDoc)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [docId]);

  if (loading) return <div className="loading">Đang tải tài liệu…</div>;

  if (error) {
    return (
      <div className="wrap">
        <div className="alert alert-error" style={{ marginTop: 26 }}>
          {error}
        </div>
        <Link className="back-link" to="/tai-lieu">
          <BackIcon style={{ width: 15, height: 15 }} />
          Về danh sách tài liệu
        </Link>
      </div>
    );
  }

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>{doc.title}</h1>
        <p>
          {doc.section || 'Tài liệu'} · phiên bản <span className="mono">{doc.version}</span> ·{' '}
          {doc.so_ky_tu.toLocaleString('vi-VN')} ký tự
        </p>
      </div>

      <article className="panel tl-doc">{dungMarkdown(doc.noi_dung)}</article>

      <Link className="back-link" to="/tai-lieu">
        <BackIcon style={{ width: 15, height: 15 }} />
        Về danh sách tài liệu
      </Link>
    </div>
  );
}
