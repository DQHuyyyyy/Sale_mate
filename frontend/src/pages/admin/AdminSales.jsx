import { useCallback, useEffect, useState } from 'react';
import { getAllSales, getSales, setSaleAccountActive } from '../../api';
import AddSaleForm from '../../components/AddSaleForm';
import SaleTable from '../../components/SaleTable';
import SoldTable from '../../components/SoldTable';

/** Trang admin: quản lý tài khoản sale + toàn bộ căn đã bán. */
export default function AdminSales() {
  const [sales, setSales] = useState([]);
  const [sold, setSold] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [salesData, soldData] = await Promise.all([getSales(), getAllSales()]);
      setSales(salesData);
      setSold(soldData);
      setError('');
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleCreated = (created) => {
    setShowForm(false);
    setNotice(`Đã tạo tài khoản @${created.username} cho ${created.full_name}.`);
    setSales((prev) => [...prev, created]);
  };

  const handleToggleActive = async (sale) => {
    const turningOff = sale.is_active;
    if (turningOff) {
      const ok = window.confirm(
        `Vô hiệu hoá tài khoản @${sale.username}?\n\n` +
          'Người này sẽ không đăng nhập được nữa. Lịch sử bán vẫn giữ nguyên và ' +
          'bạn có thể bật lại bất cứ lúc nào.',
      );
      if (!ok) return;
    }

    setBusyId(sale.id);
    setError('');
    try {
      const updated = await setSaleAccountActive(sale.id, !sale.is_active);
      setSales((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setNotice(
        updated.is_active
          ? `Đã bật lại tài khoản @${updated.username}.`
          : `Đã vô hiệu hoá tài khoản @${updated.username}.`,
      );
    } catch (toggleError) {
      setError(toggleError.message);
    } finally {
      setBusyId(null);
    }
  };

  const activeCount = sales.filter((sale) => sale.is_active).length;

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Quản lý Sale</h1>
        <p>Tạo tài khoản cho nhân viên, tắt tài khoản khi nghỉ việc, và xem toàn bộ căn đã bán.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {notice && <div className="alert alert-ok">{notice}</div>}

      {showForm && (
        <AddSaleForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />
      )}

      <div className="panel">
        <div className="sec-hd">
          <h2>Nhân viên sale</h2>
          <span className="count">
            {loading ? 'Đang tải…' : `${activeCount} đang hoạt động / ${sales.length} tài khoản`}
          </span>
          {!showForm && (
            <button
              className="btn btn-primary"
              style={{ marginLeft: 'auto' }}
              onClick={() => {
                setNotice('');
                setShowForm(true);
              }}
            >
              Thêm tài khoản
            </button>
          )}
        </div>

        <SaleTable
          sales={sales}
          loading={loading}
          onToggleActive={handleToggleActive}
          busyId={busyId}
        />
      </div>

      <div className="panel" id="sold">
        <h2>Căn đã bán toàn hệ thống</h2>
        <p className="sub">
          Sắp xếp theo thời điểm bán, mới nhất lên trước. Tài khoản bị tắt vẫn hiện đầy đủ ở đây.
        </p>
        <SoldTable records={sold} loading={loading} showSale />
      </div>
    </div>
  );
}
