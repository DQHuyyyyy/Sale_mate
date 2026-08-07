"""Unit tests cho hệ thống Evaluation (Đo lường Chất lượng & Tốc độ)."""

from __future__ import annotations

import pytest

from scripts.eval_rag_pipeline import calculate_p90, run_rag_evaluation


def test_calculate_p90():
    """Kiểm tra hàm tính toán chỉ số P90 Latency."""
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p90 = calculate_p90(latencies)
    assert p90 == 90.0


@pytest.mark.asyncio
async def test_run_rag_evaluation_metrics():
    """Kiểm tra chạy benchmark RAG trả ra đủ chỉ số Hit Rate@k, Refusal Accuracy và Latency."""
    results = await run_rag_evaluation()

    assert results["total_test_cases"] == 18
    assert results["hit_rate_at_3_pct"] == 100.0
    assert results["hit_rate_at_5_pct"] == 100.0
    assert results["refusal_accuracy_pct"] == 100.0
    assert results["latency_ms"]["mean_total"] > 0.0
    assert "tra_cuu_don" in results["category_breakdown"]
    assert "rang_buoc_so" in results["category_breakdown"]
    assert "so_sanh_nhieu_can" in results["category_breakdown"]
    assert "cau_hoi_bay_out_of_context" in results["category_breakdown"]
