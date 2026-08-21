import { useState } from 'react';
import { ExternalLinkIcon } from './Icons';

/** Fallback image khi bài viết không có ảnh hoặc ảnh lỗi */
const DEFAULT_NEWS_IMAGE = '/media/ocean-park-tong-quan.jpg';

export default function NewsCard({ item }) {
  const [imgSrc, setImgSrc] = useState(item.image_url || DEFAULT_NEWS_IMAGE);

  const getSourceBadgeClass = (source) => {
    switch (source?.toLowerCase()) {
      case 'vnexpress':
        return 'news-badge news-badge-vne';
      case 'cafef':
        return 'news-badge news-badge-cafef';
      case 'dân trí':
      case 'dantri':
        return 'news-badge news-badge-dantri';
      case 'vietnamnet':
        return 'news-badge news-badge-vnn';
      case 'vtc news':
        return 'news-badge news-badge-vtc';
      case 'tuổi trẻ':
        return 'news-badge news-badge-tuoitre';
      default:
        return 'news-badge';
    }
  };

  return (
    <article className="news-card">
      <a
        href={item.link}
        target="_blank"
        rel="noopener noreferrer"
        className="news-card-media"
      >
        <img
          src={imgSrc}
          alt={item.title}
          loading="lazy"
          onError={() => setImgSrc(DEFAULT_NEWS_IMAGE)}
        />
        <span className={getSourceBadgeClass(item.source)}>
          {item.source}
        </span>
      </a>

      <div className="news-card-body">
        {item.pub_date && (
          <div className="news-card-date">
            <span>{item.pub_date}</span>
          </div>
        )}

        <h3 className="news-card-title">
          <a href={item.link} target="_blank" rel="noopener noreferrer">
            {item.title}
          </a>
        </h3>

        {item.summary && (
          <p className="news-card-summary">
            {item.summary}
          </p>
        )}

        <div className="news-card-footer">
          <a
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="news-card-link"
          >
            Đọc bài viết gốc <ExternalLinkIcon className="news-link-icon" />
          </a>
        </div>
      </div>
    </article>
  );
}
