import { useCallback, useEffect, useState } from 'react';
import { searchApartments } from '../api';
import ApartmentList from '../components/ApartmentList';
import SearchFilters from '../components/SearchFilters';
import { uniqueTypes } from '../utils/format';

/** Trang chủ: bộ lọc + lưới căn hộ. Backend chỉ trả căn "Còn". */
export default function Search() {
  const [apartments, setApartments] = useState([]);
  const [types, setTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

  useEffect(() => {
    runSearch();
  }, [runSearch]);

  return (
    <>
      <div className="hero">
        <div className="wrap">
          <h1>Tìm căn hộ đang mở bán</h1>
          <p>Lọc theo tòa và khoảng giá — chỉ hiển thị căn còn hàng.</p>
          <SearchFilters onSearch={runSearch} loading={loading} types={types} />
        </div>
      </div>

      <div className="wrap">
        <section>
          <div className="sec-hd">
            <h2>Căn hộ còn hàng</h2>
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
