import ApartmentCard from './ApartmentCard';

export default function ApartmentList({ apartments, loading }) {
  if (loading) return <div className="loading">Đang tải danh sách căn hộ…</div>;

  if (!apartments.length) {
    return (
      <div className="grid">
        <div className="empty">Không có căn phù hợp với bộ lọc. Thử mở rộng khoảng giá.</div>
      </div>
    );
  }

  return (
    <div className="grid">
      {apartments.map((apartment) => (
        <ApartmentCard key={apartment.ma_can} apartment={apartment} />
      ))}
    </div>
  );
}
