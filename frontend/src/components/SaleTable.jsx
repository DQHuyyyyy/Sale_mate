import { formatDateTime, orDash } from '../utils/format';

/**
 * Danh sách nhân viên sale (khu vực admin).
 * `onToggleActive` có thì hiện thêm cột trạng thái và nút bật/tắt tài khoản.
 */
export default function SaleTable({ sales, loading, onToggleActive, busyId }) {
  if (loading) return <div className="loading">Đang tải danh sách sale…</div>;
  if (!sales.length) return <div className="empty">Chưa có tài khoản sale nào.</div>;

  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>Họ tên</th>
            <th>Tài khoản</th>
            <th>Điện thoại</th>
            <th>Email</th>
            <th>Ngày tạo</th>
            {onToggleActive && <th>Trạng thái</th>}
            {onToggleActive && <th />}
          </tr>
        </thead>
        <tbody>
          {sales.map((sale) => (
            <tr key={sale.id} style={sale.is_active ? undefined : { opacity: 0.55 }}>
              <td className="cell-strong">{sale.full_name}</td>
              <td className="mono">@{sale.username}</td>
              <td>{orDash(sale.phone)}</td>
              <td>{orDash(sale.email)}</td>
              <td className="cell-muted">{formatDateTime(sale.created_at)}</td>

              {onToggleActive && (
                <td>
                  <span className="ltag">{sale.is_active ? 'Đang hoạt động' : 'Đã tắt'}</span>
                </td>
              )}

              {onToggleActive && (
                <td>
                  <button
                    className="btn btn-ghost"
                    disabled={busyId === sale.id}
                    onClick={() => onToggleActive(sale)}
                  >
                    {busyId === sale.id
                      ? 'Đang lưu…'
                      : sale.is_active
                        ? 'Vô hiệu hoá'
                        : 'Bật lại'}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
