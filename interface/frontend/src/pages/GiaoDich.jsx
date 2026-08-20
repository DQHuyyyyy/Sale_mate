import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { doiTrangThaiLead, getAllSales, getDatCocLeads, getMySales } from '../api';
import SoldTable from '../components/SoldTable';
import { useAuth } from '../context/AuthContext';
import { formatDateTime } from '../utils/format';
import { lopTrangThai, nhanTrangThai } from '../utils/trangThai';

/**
 * Giao dịch — hai nửa của cùng một phễu, trên một màn hình.
 *
 * Trên: lead đặt cọc (khách đã để lại số, chưa chốt).
 * Dưới: căn đã bán (đã chốt xong).
 *
 * Trước đây là hai mục menu riêng, và tách ra không nói lên điều gì: người dùng
 * mở màn này để trả lời đúng một câu — "có gì cần gọi, và tháng này bán được
 * bao nhiêu". Hai bảng cạnh nhau trả lời được, hai trang thì phải nhớ mà bấm
 * qua lại.
 *
 * Admin thấy tất, sale chỉ thấy phần của mình. Phân quyền thật nằm ở backend;
 * ở đây chỉ đổi tiêu đề cho khớp thứ người dùng đang nhìn.
 */

const NHAN_LEAD = {
  new: 'Mới',
  da_goi: 'Đã gọi',
  da_coc: 'Đã nhận cọc',
  bo: 'Đã huỷ',
  da_ban: 'Đã bán',
};

const BO_LOC = [
  { ma: '', nhan: 'Tất cả' },
  { ma: 'new', nhan: 'Mới' },
  { ma: 'da_goi', nhan: 'Đã gọi' },
  { ma: 'da_coc', nhan: 'Đã nhận cọc' },
  { ma: 'bo', nhan: 'Đã huỷ' },
  { ma: 'da_ban', nhan: 'Đã bán' },
];

/**
 * Bước tiếp hợp lý cho từng trạng thái, theo đúng thứ tự sale làm việc.
 *
 * `da_ban` là trạng thái CUỐI — không có đường ra. Bán rồi thì đã có bản ghi
 * trong `sales_history` và căn đã khoá; cho bấm ngược lại chỉ tạo ra một giao
 * dịch mồ côi không ai gỡ được từ màn này.
 */
const BUOC_TIEP = {
  new: ['da_goi', 'da_coc', 'da_ban', 'bo'],
  da_goi: ['da_coc', 'da_ban', 'bo'],
  da_coc: ['da_ban', 'bo'],
  bo: ['new'],
  da_ban: [],
};

/** Chốt bán là hành động KHÔNG lùi lại được — hỏi lại một câu trước khi ghi. */
const XAC_NHAN_BAN = (lead) =>
  `Ghi nhận đã bán căn ${lead.ma_can} cho ${lead.ho_ten || 'khách'} (${lead.so_dien_thoai})?

` +
  'Căn sẽ chuyển sang "Đã bán" và ghi vào lịch sử bán theo giá niêm yết. ' +
  'Thao tác này không hoàn tác được từ màn này.';

export default function GiaoDich() {
  const { isAdmin } = useAuth();
  const [leads, setLeads] = useState([]);
  const [soldRecords, setSoldRecords] = useState([]);
  const [loc, setLoc] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingSold, setLoadingSold] = useState(true);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);

  const loadLeads = useCallback(async () => {
    setLoading(true);
    try {
      setLeads(await getDatCocLeads({ trangThai: loc || undefined }));
      setError('');
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [loc]);

  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  useEffect(() => {
    // Admin xem toàn hệ thống, sale xem của mình — hai endpoint khác nhau.
    (isAdmin ? getAllSales() : getMySales())
      .then(setSoldRecords)
      .catch((loadError) => setError(loadError.message))
      .finally(() => setLoadingSold(false));
  }, [isAdmin]);

  const doiTrangThai = async (lead, trangThaiMoi) => {
    // eslint-disable-next-line no-alert
    if (trangThaiMoi === 'da_ban' && !window.confirm(XAC_NHAN_BAN(lead))) return;
    setBusyId(lead.id);
    try {
      const capNhat = await doiTrangThaiLead(lead.id, trangThaiMoi);
      // Thay tại chỗ thay vì tải lại cả danh sách: người dùng đang đọc dở một
      // hàng, danh sách nhảy về đầu là mất chỗ. Dòng lead Ở LẠI sau khi chốt
      // bán — đó là lịch sử của một giao dịch có thật.
      setLeads((truoc) => truoc.map((l) => (l.id === capNhat.id ? capNhat : l)));
      setError('');
      // Bảng dưới vừa có thêm một dòng, nạp lại để hai bảng khớp nhau.
      if (trangThaiMoi === 'da_ban') {
        (isAdmin ? getAllSales() : getMySales()).then(setSoldRecords).catch(() => {});
      }
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Giao dịch</h1>
        <p>
          {isAdmin
            ? 'Toàn bộ lead đặt cọc và căn đã bán của cả hệ thống, kèm sale phụ trách.'
            : 'Lead đang chờ bạn gọi và những căn bạn đã chốt.'}
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="panel">
        <h2>Lead đặt cọc</h2>
        <p className="sub">
          Đổi trạng thái ở đây là tình trạng căn đổi theo ngay, cả ở trang tìm kiếm lẫn trong
          khung chat. “Đã huỷ” trả căn về trạng thái Còn; “Đã bán” chốt luôn giao dịch và ghi
          xuống bảng bên dưới.
        </p>

        <div className="lead-loc">
          {BO_LOC.map((muc) => (
            <button
              key={muc.ma || 'tat-ca'}
              type="button"
              className={`chip${loc === muc.ma ? ' chip-chon' : ''}`}
              onClick={() => setLoc(muc.ma)}
            >
              {muc.nhan}
            </button>
          ))}
        </div>

        {loading && <div className="loading">Đang tải danh sách lead…</div>}
        {!loading && leads.length === 0 && <div className="empty">Chưa có lead nào ở trạng thái này.</div>}

        {!loading && leads.length > 0 && (
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Căn</th>
                  <th>Tình trạng căn</th>
                  <th>Khách</th>
                  <th>Điện thoại</th>
                  <th>Ghi chú</th>
                  {isAdmin && <th>Sale phụ trách</th>}
                  <th>Nhận lúc</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => (
                  <tr key={lead.id}>
                    <td className="cell-strong mono">
                      <Link to={`/apartments/${encodeURIComponent(lead.ma_can)}`}>{lead.ma_can}</Link>
                    </td>
                    <td>
                      <span className={`ttag ${lopTrangThai(lead.tinh_trang_can)}`}>
                        {nhanTrangThai(lead.tinh_trang_can)}
                      </span>
                    </td>
                    <td>{lead.ho_ten || '—'}</td>
                    <td>{lead.so_dien_thoai}</td>
                    <td>{lead.ghi_chu || '—'}</td>
                    {/* Lead không có sale là khách CHƯA AI NHẬN — nói thẳng ra
                        thay vì để một ô trống, vì đó là hàng cần gọi trước. */}
                    {isAdmin && <td>{lead.sale_ten || 'Khách tự đặt'}</td>}
                    <td>{formatDateTime(lead.created_at)}</td>
                    <td>{NHAN_LEAD[lead.trang_thai] ?? lead.trang_thai}</td>
                    <td>
                      <div className="lead-nut">
                        {(BUOC_TIEP[lead.trang_thai] ?? []).map((buoc) => (
                          <button
                            key={buoc}
                            type="button"
                            className="btn-nho"
                            disabled={busyId === lead.id}
                            onClick={() => doiTrangThai(lead, buoc)}
                          >
                            {NHAN_LEAD[buoc]}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel" id="sold">
        <h2>{isAdmin ? 'Căn đã bán toàn hệ thống' : 'Căn bạn đã bán'}</h2>
        <SoldTable
          records={soldRecords}
          loading={loadingSold}
          showSale={isAdmin}
          emptyText={isAdmin ? 'Chưa có căn nào được bán.' : 'Bạn chưa ghi nhận căn nào đã bán.'}
        />
      </div>
    </div>
  );
}
