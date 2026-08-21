"""Test lọc nguồn — chỉ giữ thứ câu trả lời thật sự dùng.

Ca thật trên production: hỏi "Căn ở Ocean Park 1", trả lời ba căn OP1, mà dòng
nguồn liệt kê tổng quan OP2, tổng quan OP3, ưu đãi OP2 và cả description của
tool. Trích nguồn vốn để chứng minh trợ lý không bịa; chỉ vào thứ không liên
quan thì người đọc mất niềm tin vào cả những nguồn đúng.
"""

from __future__ import annotations

from src.agents.nguon import TOI_DA_NGUON_TAI_LIEU, loc_nguon_da_dung
from src.models.chat import Citation


def _doc(ten: str) -> Citation:
    return Citation(doc_id=ten, title=ten, kind="doc")


def _db(ma: str) -> Citation:
    return Citation(doc_id="inventory:postgres", title=ma, kind="db")


class TestNguonDuLieu:
    def test_chi_giu_ma_can_co_trong_cau_tra_loi(self) -> None:
        nguon = [_db("VOP758"), _db("VOP285"), _db("VOP893")]

        giu = loc_nguon_da_dung(nguon, "Căn VOP758 và VOP285 đều còn trống.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP758", "VOP285"]

    def test_khong_khop_ma_gan_giong(self) -> None:
        """VOP61 không được ăn theo VOP619.

        Phải có ít nhất một mã khớp, nếu không lưới dự phòng sẽ giữ lại tất cả
        và che mất đúng thứ test này muốn kiểm.
        """
        giu = loc_nguon_da_dung([_db("VOP61"), _db("VOP619")], "Căn VOP619 giá 3,850 tỷ.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP619"]

    def test_khong_phan_biet_hoa_thuong(self) -> None:
        giu = loc_nguon_da_dung([_db("VOP758")], "căn vop758 còn trống", co_du_lieu_tool=True)

        assert len(giu) == 1

    def test_khong_xoa_sach_khi_cau_tra_loi_khong_nhac_ma(self) -> None:
        """Không nhắc lại mã không có nghĩa là số liệu tự nhiên mà có."""
        nguon = [_db("VOP345")]

        giu = loc_nguon_da_dung(nguon, "Căn này giá 2,7 tỷ, vẫn còn trống.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP345"]

    def test_luoi_du_phong_cung_co_tran(self) -> None:
        nguon = [_db(f"VOP{i:03d}") for i in range(1, 10)]

        giu = loc_nguon_da_dung(nguon, "Có 9 căn phù hợp.", co_du_lieu_tool=True)

        assert len(giu) == TOI_DA_NGUON_TAI_LIEU


class TestChuaKhangDinhGi:
    """Lưới an toàn chỉ cứu KHẲNG ĐỊNH. Chưa nói gì thì không có gì để chứng minh."""

    def test_hoi_nguoc_de_lam_ro_thi_khong_trich_nguon(self) -> None:
        """Ca thật: hỏi "Căn ở Ocean Park 1", tool trả 23 căn, trợ lý hỏi lại
        tiêu chí — mà dòng nguồn vẫn dựng lên VOP758, VOP285, VOP619."""
        nguon = [_db(m) for m in ("VOP758", "VOP285", "VOP619")]
        tra_loi = (
            "Bạn muốn tìm căn ở Ocean Park 1 theo tiêu chí nào: số phòng ngủ, "
            "ngân sách, diện tích, tòa, hướng hay view? Mình sẽ lọc danh sách "
            "căn còn bán phù hợp cho bạn."
        )

        assert loc_nguon_da_dung(nguon, tra_loi, co_du_lieu_tool=True) == []

    def test_chu_so_tran_khong_tinh_la_so_lieu(self) -> None:
        """ "Ocean Park 1" có chữ số nhưng không khẳng định gì về căn."""
        giu = loc_nguon_da_dung([_db("VOP345")], "Bạn quan tâm Ocean Park 1 hay 3?", co_du_lieu_tool=True)

        assert giu == []

    def test_van_giu_khi_cau_tra_loi_neu_so_lieu(self) -> None:
        """Chốt ngược: có con số kèm đơn vị thì lưới an toàn vẫn phải bật."""
        giu = loc_nguon_da_dung([_db("VOP345")], "Giá khoảng 2,7 tỷ đồng.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP345"]


class TestNguonTaiLieu:
    def test_luot_co_tool_thi_tai_lieu_phai_duoc_nhac_den(self) -> None:
        """Ca trong ảnh: trả lời về căn OP1, nguồn lại có tài liệu OP2 và OP3."""
        nguon = [
            _doc("Tổng quan dự án Vinhomes Ocean Park 2"),
            _doc("Ưu đãi của Vinhomes OceanPark 2"),
            _db("VOP758"),
        ]

        giu = loc_nguon_da_dung(nguon, "Căn VOP758 giá 2,750 tỷ.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP758"]

    def test_luot_khong_co_tool_thi_giu_vai_tai_lieu_dau(self) -> None:
        """Không có tool thì câu trả lời chắc chắn dựng từ tài liệu."""
        nguon = [_doc(f"Tài liệu {i}") for i in range(6)]

        giu = loc_nguon_da_dung(nguon, "Dự án có biển hồ nước mặn.", co_du_lieu_tool=False)

        assert [c.title for c in giu] == ["Tài liệu 0", "Tài liệu 1", "Tài liệu 2"]

    def test_giu_tai_lieu_model_trich_ten_tuong_minh(self) -> None:
        nguon = [_doc("Chính sách hỗ trợ lãi suất chung của Vinhomes"), _db("VOP758")]
        tra_loi = "Theo Chính sách hỗ trợ lãi suất chung của Vinhomes, căn VOP758 được hỗ trợ."

        giu = loc_nguon_da_dung(nguon, tra_loi, co_du_lieu_tool=True)

        assert len(giu) == 2

    def test_so_khop_ten_tai_lieu_bo_qua_dau(self) -> None:
        giu = loc_nguon_da_dung([_doc("Vị trí Ocean Park")], "Theo vi tri ocean park thì...", co_du_lieu_tool=True)

        assert len(giu) == 1


class TestBienAnToan:
    def test_chua_co_chu_nao_thi_giu_nguyen(self) -> None:
        """Lỗi giữa chừng không được biến thành 'câu trả lời không có nguồn'."""
        nguon = [_doc("Tài liệu A"), _db("VOP758")]

        assert loc_nguon_da_dung(nguon, "", co_du_lieu_tool=True) == nguon

    def test_bo_nguon_khong_co_nhan(self) -> None:
        giu = loc_nguon_da_dung([Citation(doc_id="x", title="", kind="doc")], "abc", co_du_lieu_tool=False)

        assert giu == []


class TestTuChoiThiKhongCoNguon:
    """Từ chối mà vẫn trưng nguồn là tự phủ định trước mặt khách.

    Ca thật: "mình chưa có đủ dữ liệu về chính sách hỗ trợ lãi suất" đứng ngay
    trên "Nguồn: Chính sách hỗ trợ lãi suất chung của Vinhomes". Người dùng thấy
    trợ lý đang cầm đúng thứ họ cần mà không chịu đưa.
    """

    def test_model_tu_choi_bang_loi_rieng(self) -> None:
        tra_loi = (
            "Hiện tại, mình chưa có đủ dữ liệu để trả lời chính xác về chính sách hỗ trợ lãi "
            "suất chung của Vinhomes. Ngữ cảnh chỉ cung cấp thông tin về một số gói hỗ trợ cụ thể."
        )

        assert (
            loc_nguon_da_dung([_doc("Chính sách hỗ trợ lãi suất chung của Vinhomes")], tra_loi, co_du_lieu_tool=False)
            == []
        )

    def test_loi_moi_neu_them_thong_tin_cung_la_tu_choi(self) -> None:
        tra_loi = "Bạn cho mình thêm thông tin chi tiết nhé — mình tra được theo phân khu, khoảng giá hoặc mã căn."

        assert loc_nguon_da_dung([_doc("Tài liệu A")], tra_loi, co_du_lieu_tool=False) == []

    def test_cau_tra_loi_that_van_giu_nguon(self) -> None:
        """Trả lời có nội dung mà kèm ghi chú thiếu sót thì KHÔNG phải từ chối."""
        tra_loi = (
            "Dựa trên ngữ cảnh, Vinhomes đang áp dụng các chính sách hỗ trợ lãi suất như sau. "
            "Gói 18 tháng được miễn lãi hoàn toàn. Các gói từ 24 đến 60 tháng, khách hàng có thể "
            "chọn mức vay 70% hoặc 80% giá trị sản phẩm với các mức lãi suất ưu đãi khác nhau. "
            "Sau khi hết ưu đãi, Vinhomes hỗ trợ khóa trần lãi suất tối đa 9%/năm trong 2 năm. "
            "Chính sách khóa trần lãi suất mức 6%/năm trong vòng 5 năm, áp dụng từ 20/4/2026."
        )
        nguon = [_doc("Chính sách hỗ trợ lãi suất chung của Vinhomes")]

        assert loc_nguon_da_dung(nguon, tra_loi, co_du_lieu_tool=False) == nguon

    def test_cau_ngan_khong_co_cum_tu_choi_van_giu_nguon(self) -> None:
        giu = loc_nguon_da_dung([_db("VOP731")], "Căn VOP731 giá 4,050 tỷ.", co_du_lieu_tool=True)

        assert len(giu) == 1


class TestNguonTongHop:
    """Câu trả lời TỔNG HỢP không có mã căn nào để trỏ vào.

    Ca thật (ảnh 4): "Ocean Park 3 hiện còn 30 căn đang bán" mà dòng Nguồn ghi
    "inventory_summary", "VOP174", "VOP680", "VOP345" — ba mã lấy mẫu, không mã
    nào là bằng chứng cho con số 30.
    """

    def test_nhan_tong_hop_khong_can_xuat_hien_trong_cau_tra_loi(self) -> None:
        nguon = [Citation(doc_id="inventory:postgres", title="Dữ liệu tồn kho", kind="db")]

        giu = loc_nguon_da_dung(nguon, "Ocean Park 3 hiện còn 30 căn đang bán.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["Dữ liệu tồn kho"]

    def test_ma_can_khong_duoc_nhac_van_bi_loai(self) -> None:
        """Có nguồn tổng hợp rồi thì lưới dự phòng không được kéo mã căn về."""
        nguon = [
            Citation(doc_id="inventory:postgres", title="Dữ liệu tồn kho", kind="db"),
            _db("VOP758"),
        ]

        giu = loc_nguon_da_dung(nguon, "Ocean Park 3 hiện còn 30 căn đang bán.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["Dữ liệu tồn kho"]


class TestMotTaiLieuMotDong:
    """Ca thật: dòng "Nguồn" hiện y hệt một cái tên BA LẦN.

    `RetrieveNode` tạo một `Citation` cho MỖI CHUNK, và truy hồi thường lấy 3-5
    đoạn của cùng một tài liệu. Ba đoạn của một tài liệu vẫn chỉ trỏ về một chỗ
    để người đọc mở ra kiểm — trùng ở đây là trùng NGUỒN, không phải trùng bằng
    chứng.
    """

    def test_ba_doan_cung_tai_lieu_ra_mot_dong(self) -> None:
        nguon = [_doc("Chính sách hỗ trợ lãi suất chung của Vinhomes") for _ in range(3)]

        giu = loc_nguon_da_dung(nguon, "Trần lãi suất 6%/năm trong 5 năm.", co_du_lieu_tool=False)

        assert [c.title for c in giu] == ["Chính sách hỗ trợ lãi suất chung của Vinhomes"]

    def test_tai_lieu_gop_nhieu_doan_nhat_dung_dau(self) -> None:
        """Người đọc thấy hai cái tên thì câu hỏi đầu tiên là "tin cái nào" —
        thứ tự phải trả lời được câu đó.

        Đo thật: điểm rerank gần bằng nhau (0,650 vs 0,620) nên không tách được
        bằng điểm, nhưng số đoạn thì rõ — 4/5 so với 1/5.
        """
        nguon = [
            _doc("Chính sách hỗ trợ lãi suất chung của Vinhomes"),
            _doc("Pháp lý & thủ tục sang tên"),
            _doc("Chính sách hỗ trợ lãi suất chung của Vinhomes"),
            _doc("Chính sách hỗ trợ lãi suất chung của Vinhomes"),
        ]

        giu = loc_nguon_da_dung(nguon, "Vinhomes khoá trần lãi suất 6%/năm.", co_du_lieu_tool=False)

        assert giu[0].title == "Chính sách hỗ trợ lãi suất chung của Vinhomes"
        assert len(giu) == 2

    def test_ma_can_khong_bi_xao_tron(self) -> None:
        """Mỗi căn đúng một citation nên cùng số đoạn — `sorted` ổn định phải
        giữ nguyên thứ tự người đọc thấy trong câu trả lời."""
        nguon = [_db("VOP758"), _db("VOP285"), _db("VOP619")]

        giu = loc_nguon_da_dung(nguon, "Căn VOP758, VOP285 và VOP619 đều còn.", co_du_lieu_tool=True)

        assert [c.title for c in giu] == ["VOP758", "VOP285", "VOP619"]

    def test_tran_3_dem_tai_lieu_khong_dem_doan(self) -> None:
        """Trước đây trần đếm chunk, nên 3 đoạn của một tài liệu đã chạm trần và
        hai tài liệu khác bị loại oan."""
        nguon = [_doc("A"), _doc("A"), _doc("A"), _doc("B"), _doc("C")]

        giu = loc_nguon_da_dung(nguon, "Dự án có biển hồ nước mặn.", co_du_lieu_tool=False)

        assert [c.title for c in giu] == ["A", "B", "C"]


class TestTraLoiMotPhan:
    """Câu vừa KHẲNG ĐỊNH vừa xin thêm thông tin — không phải từ chối.

    Ca thật ở nhánh tính vay: "Căn VOP962 giá 2,7 tỷ. Vay 70% khoảng 1,89 tỷ.
    Mình chưa có đủ dữ liệu về lãi suất để tính trả hàng tháng." Có cụm từ chối,
    lại ngắn dưới ngưỡng 400 ký tự, nên bị gọi là từ chối và mất sạch nguồn —
    đúng lúc hai con số đó là thứ khách sẽ mang đi hỏi ngân hàng.
    """

    TRA_LOI = (
        "Căn VOP962 có giá 2,7 tỷ đồng. Vay 70% khoảng 1,89 tỷ đồng. "
        "Mình chưa có đủ dữ liệu về lãi suất ngân hàng để tính khoản trả hàng tháng."
    )

    def test_van_giu_nguon_cho_con_so_da_neu(self) -> None:
        nguon = [_db("VOP962")]

        assert [c.title for c in loc_nguon_da_dung(nguon, self.TRA_LOI, co_du_lieu_tool=True)] == ["VOP962"]

    def test_van_la_tu_choi_theo_bo_eval(self) -> None:
        """`la_loi_tu_choi` KHÔNG đổi — bộ eval chấm cột `phai_tu_choi` bằng
        chính hàm này, đổi định nghĩa là đổi luôn số đo lịch sử."""
        from src.agents.nguon import la_loi_tu_choi

        assert la_loi_tu_choi(self.TRA_LOI) is True

    def test_tu_choi_thuan_van_khong_co_nguon(self) -> None:
        """Chốt ngược: câu từ chối KHÔNG khẳng định gì thì vẫn phải sạch nguồn."""
        tra_loi = "Mình chưa có đủ dữ liệu để trả lời câu này. Bạn cho mình thêm thông tin nhé."

        assert loc_nguon_da_dung([_doc("Tài liệu A")], tra_loi, co_du_lieu_tool=False) == []


class TestModelVietTenRutGon:
    """Ca thật: câu trả lời nêu trần 6%/năm và các gói 18/24/30/36/60 tháng, mà
    dòng "Nguồn" không có tài liệu chính sách nào.

    Tài liệu tên "Chính sách hỗ trợ lãi suất chung của Vinhomes", model trích
    `[Chính sách hỗ trợ lãi suất]` — thiếu bốn chữ cuối. Luật cũ đòi tên đầy đủ
    nằm nguyên trong câu nên loại nó, và mọi con số vừa nêu đứng đó không nguồn.
    """

    TEN = "Chính sách hỗ trợ lãi suất chung của Vinhomes"

    def test_nhan_ten_rut_gon_trong_dau_trich(self) -> None:
        tra_loi = "Vay 70% khoảng 1,89 tỷ đồng. [Chính sách hỗ trợ lãi suất]"

        giu = loc_nguon_da_dung([_doc(self.TEN)], tra_loi, co_du_lieu_tool=True)

        assert [c.title for c in giu] == [self.TEN]

    def test_ten_qua_ngan_thi_khong_nhan(self) -> None:
        """ "Chính sách" khớp cả bảng giá lẫn chính sách bán hàng — nhận vào là
        mở đường cho nhãn sai."""
        giu = loc_nguon_da_dung([_doc(self.TEN)], "Theo [Chính sách], vay 70%.", co_du_lieu_tool=True)

        assert giu == []

    def test_chi_nhan_trong_dau_trich_khong_quet_ca_cau(self) -> None:
        """Nhắc tên giữa câu văn xuôi là NÓI VỀ tài liệu, chưa chắc đang trích."""
        tra_loi = "Bạn nên đọc chính sách hỗ trợ lãi suất của chủ đầu tư để biết thêm chi tiết cụ thể."

        giu = loc_nguon_da_dung([_doc(self.TEN)], tra_loi, co_du_lieu_tool=True)

        assert giu == []

    def test_ten_day_du_van_khop_nhu_cu(self) -> None:
        tra_loi = f"Theo {self.TEN}, trần lãi suất là 6%/năm."

        assert len(loc_nguon_da_dung([_doc(self.TEN)], tra_loi, co_du_lieu_tool=True)) == 1
