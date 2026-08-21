"""Test loader dữ liệu tồn kho thật (CSV export từ Sheet + ảnh từ Drive).

Dùng CSV/ảnh giả trong tmp_path — không phụ thuộc data/raw/ thật (bị
.gitignore, không có sẵn trên CI hay máy đồng đội).
"""

from __future__ import annotations

from pathlib import Path

from src.data.sources.inventory import InventoryUnit, load_inventory_csv, units_to_documents

_HEADER = (
    "Ma Can (VOP),Toa,Tang,So phong,Loai can,"
    "Dien tich,Huong phong thuy,View,So do,Gia,Noi that,"
    "Tinh trang (Con/Het),Anh,,,,,,,\n"
)


def _write_csv(path: Path, rows: list[str]) -> None:
    path.write_text("﻿" + _HEADER + "".join(rows), encoding="utf-8")


def test_doc_dung_du_lieu_va_bo_qua_dong_rong(tmp_path: Path):
    csv_path = tmp_path / "inventory.csv"
    _write_csv(
        csv_path,
        [
            'VOP001,R103,27,2702,1 PN,49m2,Đông Nam,View hồ,Sẵn sổ,"3,1 tỷ",Full nội thất,Còn,1. R103\n',
            ",,,,,,,,,,,,\n",  # Excel export dư dòng trống — phải bị bỏ qua
        ],
    )

    units = load_inventory_csv(csv_path, tmp_path / "photos")

    assert len(units) == 1
    unit = units[0]
    assert unit.unit_code == "VOP001"
    assert unit.building == "R103"
    assert unit.legal_status == "Sẵn sổ"
    assert unit.status == "available"
    assert unit.photos == []


def test_chuan_hoa_tinh_trang_het_thanh_sold(tmp_path: Path):
    csv_path = tmp_path / "inventory.csv"
    _write_csv(
        csv_path,
        ['VOP003,H1,17,1715,2 PN,63m2,Đông Nam,View phố,Sẵn sổ,"4,75 tỷ",Full nội thất,Hết,3. H1\n'],
    )

    units = load_inventory_csv(csv_path, tmp_path / "photos")

    assert units[0].status == "sold"


def test_gan_dung_anh_theo_folder_cung_ten_ma_can(tmp_path: Path):
    csv_path = tmp_path / "inventory.csv"
    _write_csv(
        csv_path,
        ['VOP002,S102,20,2006,Studio,28m2,Đông Bắc,View biệt thự,Sẵn sổ,"1,8 tỷ",Full nội thất,Còn,2. S102\n'],
    )

    unit_photos_dir = tmp_path / "photos" / "VOP002"
    unit_photos_dir.mkdir(parents=True)
    (unit_photos_dir / "IMG_2.jpg").write_bytes(b"fake")
    (unit_photos_dir / "IMG_1.JPG").write_bytes(b"fake")
    (unit_photos_dir / "note.txt").write_bytes(b"fake")  # không phải ảnh

    units = load_inventory_csv(csv_path, tmp_path / "photos")

    assert units[0].photos == ["IMG_1.JPG", "IMG_2.jpg"]


def test_khong_co_folder_anh_thi_tra_danh_sach_rong(tmp_path: Path):
    csv_path = tmp_path / "inventory.csv"
    _write_csv(
        csv_path,
        ['VOP999,H1,17,1715,2 PN,63m2,Đông Nam,View phố,Sẵn sổ,"4,75 tỷ",Full nội thất,Còn,3. H1\n'],
    )

    units = load_inventory_csv(csv_path, tmp_path / "photos-khong-ton-tai")

    assert units[0].photos == []


def test_chuyen_unit_thanh_document_khong_lo_gia_va_tinh_trang():
    unit = InventoryUnit(
        unit_code="VOP398",
        building="R103",
        floor="27",
        room_no="2702",
        unit_type="1 PN, 1WC",
        area_m2="49m2",
        direction="Đông Nam",
        view="View biển hồ, biệt thự",
        legal_status="Sẵn sổ",
        price_label="3,1 tỷ",
        furniture="Full nội thất: Điều hòa, Giường",
        status="available",
        photos=["IMG_1.jpg"],
    )

    docs = units_to_documents([unit])

    assert len(docs) == 1
    doc = docs[0]
    assert doc.doc_id == "inventory:VOP398"
    assert "View biển hồ" in doc.text
    assert "Sẵn sổ" in doc.text
    # Giá và tình trạng còn/hết KHÔNG được lộ vào text embed — đã có tool
    # inventory_lookup trả lời chính xác, tránh hai nguồn số liệu lệch nhau.
    assert "3,1 tỷ" not in doc.text
    assert "available" not in doc.text
    # Tồn kho là dữ liệu nội bộ của team — chỉ Admin/Sale thấy qua RAG, portal
    # công khai không được lộ ra (đúng nguyên tắc lọc tại tầng truy hồi).
    assert doc.metadata["visibility"] == "internal"
    # Markdown có heading rõ ràng, đúng luồng Parsing -> Markdown -> Chunking.
    assert doc.text.startswith("# Căn VOP398 (R103)")
    assert "## Tầm nhìn" in doc.text
    assert "## Pháp lý" in doc.text
    assert "## Nội thất" in doc.text
