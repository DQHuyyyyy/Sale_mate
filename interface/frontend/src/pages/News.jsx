import { useEffect, useState } from 'react';
import { getNews } from '../api';
import NewsCard from '../components/NewsCard';
import { NewspaperIcon, RefreshIcon } from '../components/Icons';

export default function News() {
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedSource, setSelectedSource] = useState('all');
  const [error, setError] = useState(null);

  const fetchNewsList = async (forceRefresh = false) => {
    try {
      if (forceRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const res = await getNews({ limit: 30, refresh: forceRefresh });
      setArticles(res.items || []);
    } catch (err) {
      console.error('Lỗi tải tin tức:', err);
      setError('Không thể tải tin tức lúc này. Vui lòng thử lại sau.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchNewsList();
  }, []);

  const sources = ['all', ...new Set(articles.map((a) => a.source).filter(Boolean))];

  const filteredArticles =
    selectedSource === 'all'
      ? articles
      : articles.filter((a) => a.source.toLowerCase() === selectedSource.toLowerCase());

  return (
    <div className="wrap news-page">
      <header className="news-page-header">
        <div>
          <span className="news-eyebrow">
            <NewspaperIcon className="news-eyebrow-icon" /> Cập nhật liên tục
          </span>
          <h1>Tin tức thị trường Bất động sản</h1>
          <p className="news-page-desc">
            Tổng hợp tin tức, chính sách quy hoạch, nhận định thị trường bất động sản mới nhất từ
            các báo chính thống.
          </p>
        </div>

        <button
          className={`btn btn-ghost news-btn-refresh ${refreshing ? 'is-spinning' : ''}`}
          onClick={() => fetchNewsList(true)}
          disabled={loading || refreshing}
          title="Làm mới tin tức mới nhất"
        >
          <RefreshIcon />
          <span>{refreshing ? 'Đang cập nhật...' : 'Cập nhật tin mới'}</span>
        </button>
      </header>

      {/* Bộ lọc nguồn tin */}
      {sources.length > 1 && (
        <div className="news-filter-bar">
          <span className="news-filter-label">Nguồn tin:</span>
          <div className="news-filter-chips">
            {sources.map((src) => (
              <button
                key={src}
                className={`news-chip ${selectedSource === src ? 'active' : ''}`}
                onClick={() => setSelectedSource(src)}
              >
                {src === 'all' ? 'Tất cả nguồn' : src}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Trạng thái tải / lỗi */}
      {loading ? (
        <div className="news-grid-skeleton">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <div key={n} className="news-skeleton-card" />
          ))}
        </div>
      ) : error ? (
        <div className="news-error">
          <p>{error}</p>
          <button className="btn btn-primary" onClick={() => fetchNewsList(true)}>
            Thử lại
          </button>
        </div>
      ) : filteredArticles.length === 0 ? (
        <div className="news-empty">
          <p>Hiện chưa có bài viết nào từ nguồn này.</p>
        </div>
      ) : (
        <div className="news-grid">
          {filteredArticles.map((item) => (
            <NewsCard key={item.id || item.link} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
