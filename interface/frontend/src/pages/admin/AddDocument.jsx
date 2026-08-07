import AddDocumentForm from '../../components/AddDocumentForm';

export default function AddDocument() {
  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Thêm tài liệu</h1>
        <p>Tài liệu pháp lý, bảng giá, chính sách bán hàng cho đội sale.</p>
      </div>
      <AddDocumentForm />
    </div>
  );
}
