"""Test loader tài liệu kiến thức chung (chính sách, thủ tục, tiện ích...)."""

from __future__ import annotations

import pytest

from src.data.ingestion.metadata_schema import validate_metadata
from src.data.sources.knowledge_docs import load_knowledge_dir, load_knowledge_file

_VALID_MD = """---
title: Chính sách chiết khấu theo quý
section: Chính sách bán hàng
visibility: internal
---

Chiết khấu áp dụng theo quý, điều kiện thanh toán sớm được ưu tiên hơn.
"""


def test_doc_dung_du_truong(tmp_path):
    path = tmp_path / "chiet-khau.md"
    path.write_text(_VALID_MD, encoding="utf-8")

    doc = load_knowledge_file(path)

    assert doc.doc_id == "knowledge:chiet-khau"
    assert doc.title == "Chính sách chiết khấu theo quý"
    assert "Chiết khấu áp dụng theo quý" in doc.text
    assert doc.metadata["visibility"] == "internal"
    assert doc.metadata["section"] == "Chính sách bán hàng"
    validate_metadata(doc.metadata, doc_id=doc.doc_id)


def test_thieu_frontmatter_thi_bao_loi(tmp_path):
    path = tmp_path / "khong-co-frontmatter.md"
    path.write_text("Nội dung không có front-matter.", encoding="utf-8")

    with pytest.raises(ValueError, match="front-matter"):
        load_knowledge_file(path)


def test_thieu_khoa_bat_buoc_thi_bao_loi(tmp_path):
    path = tmp_path / "thieu-section.md"
    path.write_text("---\ntitle: T\nvisibility: public\n---\nNội dung.", encoding="utf-8")

    with pytest.raises(ValueError, match="section"):
        load_knowledge_file(path)


def test_visibility_sai_gia_tri_thi_bao_loi(tmp_path):
    path = tmp_path / "sai-visibility.md"
    path.write_text("---\ntitle: T\nsection: S\nvisibility: mo-ta\n---\nNội dung.", encoding="utf-8")

    with pytest.raises(ValueError, match="visibility"):
        load_knowledge_file(path)


def test_load_dir_doc_het_file_md_va_bo_qua_thu_muc_rong(tmp_path):
    (tmp_path / "a.md").write_text(_VALID_MD, encoding="utf-8")
    sub = tmp_path / "nhom-con"
    sub.mkdir()
    (sub / "b.md").write_text(_VALID_MD.replace("chiet-khau", "khac"), encoding="utf-8")

    docs = load_knowledge_dir(tmp_path)

    assert len(docs) == 2


def test_load_dir_thu_muc_khong_ton_tai_tra_danh_sach_rong(tmp_path):
    docs = load_knowledge_dir(tmp_path / "khong-ton-tai")

    assert docs == []
