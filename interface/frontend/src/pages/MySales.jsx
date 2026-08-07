import { useEffect, useState } from 'react';
import { getMySales } from '../api';
import SoldTable from '../components/SoldTable';

/**
 * Lịch sử bán của chính người đăng nhập.
 * Không có tham số nào để xem của người khác — backend lọc theo sale_id trong token.
 */
export default function MySales() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getMySales()
      .then(setRecords)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Lịch sử bán của tôi</h1>
        <p>Những căn do chính bạn ghi nhận đã bán, mới nhất lên trước.</p>
      </div>

      <div className="panel">
        {error ? (
          <div className="alert alert-error">{error}</div>
        ) : (
          <SoldTable
            records={records}
            loading={loading}
            emptyText="Bạn chưa ghi nhận căn nào. Mở chi tiết một căn còn hàng rồi bấm “Ghi nhận đã bán”."
          />
        )}
      </div>
    </div>
  );
}
