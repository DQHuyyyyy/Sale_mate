import { formatDateTime, orDash } from '../utils/format';

export default function DocumentList({ documents, loading }) {
  if (loading) return <div className="loading">Đang tải danh sách tài liệu…</div>;

  if (!documents.length) {
    return <div className="empty">Chưa có tài liệu nào trong nhóm này.</div>;
  }

  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Tài liệu</th>
            <th>Nhóm</th>
            <th>Người thêm</th>
            <th>Ngày thêm</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <td>
                <div className="cell-strong">{document.title}</div>
                {document.description && <div className="cell-muted">{document.description}</div>}
              </td>
              <td>{orDash(document.category)}</td>
              <td>{orDash(document.uploaded_by_name)}</td>
              <td className="cell-muted">{formatDateTime(document.created_at)}</td>
              <td>
                {document.file_url ? (
                  <a
                    className="btn btn-ghost"
                    href={document.file_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Mở tài liệu
                  </a>
                ) : (
                  <span className="cell-muted">Chưa có file</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
