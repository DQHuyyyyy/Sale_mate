import { useEffect, useState } from 'react';
import { getTowers } from '../api';
import { SearchIcon } from './Icons';

// Giới hạn giá 0–20 tỷ, khớp ràng buộc phía backend.
const PRICE_MIN = 0;
const PRICE_MAX = 20;

const DEFAULT_FILTERS = { tower: '', priceMin: '', priceMax: '', type: '', wc: '' };

// Kho hiện có 1–3 vệ sinh. Khai cứng chứ không rút từ dữ liệu như `types`: danh
// sách loại căn thay đổi theo hàng còn bán, còn số vệ sinh thì không — và rút
// động thì lúc bán hết căn 3WC ô lọc lặng lẽ mất một mục.
const SO_WC = [1, 2, 3];

export default function SearchFilters({ onSearch, loading, types = [], value }) {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [towers, setTowers] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    getTowers()
      .then(setTowers)
      .catch(() => setTowers([])); // Không có bảng towers thì để dropdown rỗng, không chặn tìm kiếm.
  }, []);

  // Bộ lọc thật nằm trên URL. Đồng bộ xuống các ô để khi trợ lý S lọc hộ, người
  // dùng nhìn thấy ĐÚNG tiêu chí đang áp dụng chứ không phải ô trống.
  const khoaUrl = JSON.stringify(value ?? {});
  useEffect(() => {
    setFilters({ ...DEFAULT_FILTERS, ...(value ?? {}) });
  }, [khoaUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (key) => (event) => setFilters({ ...filters, [key]: event.target.value });

  // Trợ lý S gửi tiền tố "2PN", mà dropdown chỉ có giá trị đầy đủ ("2PN, 1WC",
  // "2PN, 2WC"). Không thêm vào thì `<select>` không khớp mục nào và hiện "Tất
  // cả" — ô lọc nói dối về điều kiện đang chạy. Thêm đúng chuỗi đang lọc để
  // người dùng đổi sang giá trị khác được mà không mất tiêu chí hiện tại.
  const loaiCan = filters.type && !types.includes(filters.type) ? [filters.type, ...types] : types;

  const submit = (event) => {
    event.preventDefault();
    const min = filters.priceMin === '' ? null : Number(filters.priceMin);
    const max = filters.priceMax === '' ? null : Number(filters.priceMax);

    if (min !== null && max !== null && min > max) {
      setError('Giá từ đang lớn hơn giá đến. Đổi lại hai ô giá giúp mình.');
      return;
    }
    setError('');
    onSearch(filters);
  };

  return (
    <form className="filter" onSubmit={submit}>
      <div className="field">
        <label htmlFor="fTower">Tòa</label>
        <select id="fTower" value={filters.tower} onChange={update('tower')}>
          <option value="">Tất cả các tòa</option>
          {towers.map((tower) => (
            <option key={tower.code} value={tower.code}>
              Tòa {tower.code}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="fMin">Giá (tỷ VND)</label>
        <div className="price-row">
          <input
            id="fMin"
            type="number"
            min={PRICE_MIN}
            max={PRICE_MAX}
            step="0.1"
            placeholder="Từ"
            value={filters.priceMin}
            onChange={update('priceMin')}
          />
          <span>—</span>
          <input
            type="number"
            min={PRICE_MIN}
            max={PRICE_MAX}
            step="0.1"
            placeholder="Đến"
            value={filters.priceMax}
            onChange={update('priceMax')}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="fType">Loại căn</label>
        <select id="fType" value={filters.type} onChange={update('type')}>
          <option value="">Tất cả</option>
          {loaiCan.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="fWc">Vệ sinh</label>
        <select id="fWc" value={filters.wc} onChange={update('wc')}>
          <option value="">Tất cả</option>
          {SO_WC.map((so) => (
            <option key={so} value={so}>
              {so} vệ sinh
            </option>
          ))}
        </select>
      </div>

      <button className="btn-search" type="submit" disabled={loading}>
        <SearchIcon />
        {loading ? 'Đang tìm…' : 'Tìm kiếm'}
      </button>

      {error && (
        <div className="alert alert-error" style={{ gridColumn: '1/-1', margin: 0 }}>
          {error}
        </div>
      )}
    </form>
  );
}
