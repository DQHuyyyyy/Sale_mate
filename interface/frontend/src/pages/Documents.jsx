import { useEffect, useMemo, useState } from 'react';
import { getDocuments } from '../api';
import DocumentList from '../components/DocumentList';

/** Danh sách tài liệu dùng chung. Mọi tài khoản đã đăng nhập đều xem được. */
export default function Documents() {
  const [documents, setDocuments] = useState([]);
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getDocuments()
      .then(setDocuments)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, []);

  // Nhóm tài liệu lấy từ chính dữ liệu, không hardcode.
  const categories = useMemo(
    () => [...new Set(documents.map((item) => item.category).filter(Boolean))].sort(),
    [documents],
  );

  const visible = category ? documents.filter((item) => item.category === category) : documents;

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Tài liệu</h1>
        <p>Hồ sơ pháp lý, bảng giá và chính sách bán hàng do quản trị viên đăng.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="panel">
        <div className="sec-hd">
          <h2>{visible.length} tài liệu</h2>
          {categories.length > 0 && (
            <div className="field" style={{ marginLeft: 'auto', minWidth: 200 }}>
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                aria-label="Lọc theo nhóm tài liệu"
              >
                <option value="">Tất cả nhóm</option>
                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <DocumentList documents={visible} loading={loading} />
      </div>
    </div>
  );
}
