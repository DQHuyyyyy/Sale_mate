import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchApartments } from '../api';
import ApartmentList from '../components/ApartmentList';
import SearchFilters from '../components/SearchFilters';
import { uniqueTypes } from '../utils/format';

const TRUONG_LOC = ['tower', 'priceMin', 'priceMax', 'type'];

/**
 * Trang chủ: bộ lọc + lưới căn hộ. Backend chỉ trả căn "Còn".
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

  /** Bấm Tìm kiếm thì ghi bộ lọc lên URL; useEffect ở trên lo phần gọi API. */
  const doiBoLoc = (moi) => {
    const params = {};
    for (const key of TRUONG_LOC) {
      if (moi[key]) params[key] = String(moi[key]);
    }
    setSearchParams(params);
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
