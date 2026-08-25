import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchApartments } from '../api';
import ApartmentList from '../components/ApartmentList';
import SearchFilters from '../components/SearchFilters';
import { uniqueTypes } from '../utils/format';

// `priceMaxExclusive` chỉ do trợ lý S đặt (câu "dưới 3 tỷ"), form không có ô
// cho nó — ô "Đến" là một khoảng nên vẫn tính cả biên. Vẫn phải nằm trong danh
// sách này để sống sót qua URL và F5.
const TRUONG_LOC = ['tower', 'priceMin', 'priceMax', 'priceMaxExclusive', 'subdivision', 'type', 'wc'];

/**
 * Đọc loại căn thành tiếng Việt.
 *
 * Trợ lý S gửi tiền tố "2PN" khi số phòng ngủ ứng với nhiều giá trị thật trong
 * kho ("2PN, 1WC" và "2PN, 2WC"), nên chuỗi đó KHÔNG có trong dropdown và không
 * đọc lên được thành lời. Giá trị đầy đủ thì giữ nguyên — nó đã tự rõ nghĩa.
 */
function nhanLoaiCan(giaTri) {
  const chiPhongNgu = /^(\d+)\s*PN$/i.exec(giaTri);
  return chiPhongNgu ? `${chiPhongNgu[1]} phòng ngủ` : giaTri;
}

/** Khoảng giá gộp thành MỘT nhãn: ba tham số rời mô tả cùng một điều kiện. */
function nhanKhoangGia({ priceMin, priceMax, priceMaxExclusive }) {
  if (priceMin && priceMax) return `${priceMin} – ${priceMax} tỷ`;
  if (priceMin) return `Từ ${priceMin} tỷ`;
  // "dưới 3 tỷ" loại luôn căn giá đúng 3 tỷ, khác hẳn ô "Đến" trên form vốn
  // tính cả biên. Nhãn phải nói đúng điều kiện đang chạy.
  if (priceMax) return priceMaxExclusive ? `Dưới ${priceMax} tỷ` : `Đến ${priceMax} tỷ`;
  return null;
}

/**
 * Các bộ lọc đang áp dụng, dạng chip bấm để gỡ.
 *
 * Cần vì form KHÔNG hiện được hết tiêu chí: không có ô phân khu, và ô "Loại căn"
 * để trống khi trợ lý gửi tiền tố "2PN" vì chuỗi đó không khớp mục nào trong
 * dropdown. Người dùng thấy "9 căn" dưới một form ghi toàn "Tất cả" thì không
 * hiểu vì sao thiếu căn, cũng không có cách nào bỏ lọc.
 *
 * `xoa` là danh sách khoá URL cần gỡ — khoảng giá gỡ cả ba khoá một lần.
 */
function chipDangLoc(filters) {
  const chips = [];
  if (filters.subdivision) {
    chips.push({ nhan: filters.subdivision, xoa: ['subdivision'] });
  }
  if (filters.tower) chips.push({ nhan: `Tòa ${filters.tower}`, xoa: ['tower'] });
  if (filters.type) chips.push({ nhan: nhanLoaiCan(filters.type), xoa: ['type'] });
  if (filters.wc) chips.push({ nhan: `${filters.wc} vệ sinh`, xoa: ['wc'] });

  const gia = nhanKhoangGia(filters);
  if (gia) chips.push({ nhan: gia, xoa: ['priceMin', 'priceMax', 'priceMaxExclusive'] });

  return chips;
}

/**
 * Trang tìm kiếm căn hộ: bộ lọc + lưới căn hộ. Backend chỉ trả căn "Còn".
 *
 * Bộ lọc nằm trên URL chứ không trong state riêng. Nhờ vậy trợ lý S lọc được
 * danh sách này bằng cách điều hướng — người dùng hỏi "căn 2-3 tỷ" thì cả câu
 * trả lời lẫn lưới bên ngoài cùng hiện một tập căn. Tiện thể link cũng chia sẻ
 * và F5 được.
 */
export default function Search() {
  const [apartments, setApartments] = useState([]);
  const [types, setTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => {
    const value = {};
    for (const key of TRUONG_LOC) {
      const v = searchParams.get(key);
      if (v) value[key] = v;
    }
    return value;
  }, [searchParams]);

  const runSearch = useCallback(async (filters = {}) => {
    setLoading(true);
    setError('');
    try {
      const data = await searchApartments(filters);
      setApartments(data);
      // Loại căn cho dropdown lấy từ lần tải đầu (khi chưa lọc gì).
      if (!filters.tower && !filters.type && !filters.priceMin && !filters.priceMax) {
        setTypes(uniqueTypes(data));
      }
    } catch (searchError) {
      setError(searchError.message);
      setApartments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Chạy lại mỗi khi URL đổi — dù do người dùng bấm "Tìm kiếm" hay do trợ lý S
  // điều hướng sau khi trả lời.
  useEffect(() => {
    runSearch(filters);
  }, [runSearch, filters]);

  const dangLoc = Object.keys(filters).length > 0;
  const chips = chipDangLoc(filters);

  /** Bấm Tìm kiếm thì ghi bộ lọc lên URL; useEffect ở trên lo phần gọi API. */
  const doiBoLoc = (moi) => {
    const params = {};
    for (const key of TRUONG_LOC) {
      if (moi[key]) params[key] = String(moi[key]);
    }
    setSearchParams(params);
  };

  /** Gỡ một chip. Bỏ khoá khỏi URL là useEffect ở trên tự tìm lại. */
  const goBoLoc = (khoaCanXoa) => {
    const conLai = { ...filters };
    for (const khoa of khoaCanXoa) delete conLai[khoa];
    doiBoLoc(conLai);
  };

  return (
    <>
      <div className="hero">
        <div className="wrap">
          <h1>Tìm căn hộ đang mở bán</h1>
          <p>Lọc theo tòa và khoảng giá — chỉ hiển thị căn còn hàng.</p>
          <SearchFilters onSearch={doiBoLoc} loading={loading} types={types} value={filters} />
        </div>
      </div>

      <div className="wrap">
        <section>
          <div className="sec-hd">
            <h2>{dangLoc ? 'Kết quả lọc' : 'Căn hộ còn hàng'}</h2>
            {!loading && !error && <span className="count">{apartments.length} căn</span>}
          </div>

          {chips.length > 0 && (
            <div className="loc-dang-ap">
              <span className="loc-nhan">Đang lọc</span>
              {chips.map((chip) => (
                <button
                  key={chip.nhan}
                  type="button"
                  className="chip chip-go"
                  onClick={() => goBoLoc(chip.xoa)}
                  aria-label={`Bỏ lọc ${chip.nhan}`}
                >
                  {chip.nhan}
                  <span aria-hidden="true">×</span>
                </button>
              ))}
              {chips.length > 1 && (
                <button type="button" className="chip" onClick={() => setSearchParams({})}>
                  Xoá tất cả
                </button>
              )}
            </div>
          )}

          {error ? (
            <div className="alert alert-error">{error}</div>
          ) : (
            <ApartmentList apartments={apartments} loading={loading} />
          )}
        </section>
      </div>
    </>
  );
}
