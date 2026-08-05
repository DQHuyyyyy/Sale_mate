import { ZoneIcon } from './Icons';

export default function ZoneList({ zones, loading }) {
  if (loading) return <div className="loading">Đang tải sơ đồ phân khu…</div>;

  if (!zones.length) {
    return (
      <div className="zgrid">
        <div className="empty">
          Chưa có phân khu nào. Chạy migrations/003_seed.sql để tạo dữ liệu khu và tòa.
        </div>
      </div>
    );
  }

  return (
    <div className="zgrid">
      {zones.map((zone) => (
        <div className="zcard" key={zone.id}>
          <div className="zthumb">
            {zone.code && <span className="zcode">Khu {zone.code}</span>}
            {zone.image_url ? <img src={zone.image_url} alt={zone.name} /> : <ZoneIcon />}
          </div>
          <div className="zbody">
            <h3 className="zname">{zone.name}</h3>
            {zone.description && <p className="zdesc">{zone.description}</p>}
            <div className="ztowers">
              {zone.towers?.length ? `Gồm tòa: ${zone.towers.join(', ')}` : 'Chưa gán tòa nào'}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
