import AddApartmentForm from '../../components/AddApartmentForm';

export default function AddApartment() {
  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Thêm căn hộ</h1>
        <p>Ghi trực tiếp vào bảng căn hộ. Ảnh được đẩy lên Supabase Storage.</p>
      </div>
      <AddApartmentForm />
    </div>
  );
}
