import { Link } from 'react-router-dom';
import { formatDateTime, formatPrice, orDash } from '../utils/format';

/**
 * Bảng căn đã bán. `showSale` bật cột người bán — chỉ dùng ở màn admin,
 * còn "Lịch sử bán của tôi" thì không cần.
 */
export default function SoldTable({ records, loading, showSale = false, emptyText }) {
  if (loading) return <div className="loading">Đang tải lịch sử bán…</div>;
  if (!records.length) return <div className="empty">{emptyText || 'Chưa có căn nào được bán.'}</div>;

  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Mã căn</th>
            <th>Vị trí</th>
            <th>Loại căn</th>
            {showSale && <th>Người bán</th>}
            <th>Khách hàng</th>
            <th>Giá bán</th>
            <th>Thời điểm</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id}>
              <td className="cell-strong mono">
                <Link to={`/apartments/${encodeURIComponent(record.ma_can)}`}>{record.ma_can}</Link>
              </td>
              <td>
                Tòa {orDash(record.toa)}
                {record.tang !== null && record.tang !== undefined ? ` · T${record.tang}` : ''}
              </td>
              <td>{orDash(record.loai_can)}</td>
              {showSale && (
                <td>
                  <div className="cell-strong">{orDash(record.full_name)}</div>
                  <div className="cell-muted mono">@{record.username}</div>
                </td>
              )}
              <td>
                <div>{orDash(record.customer_name)}</div>
                <div className="cell-muted">{orDash(record.customer_phone)}</div>
              </td>
              <td className="cell-price">{formatPrice(null, record.sold_price)}</td>
              <td className="cell-muted">{formatDateTime(record.sold_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
