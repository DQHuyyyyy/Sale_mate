"""Kiểm tra endpoint /api/news."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_news_endpoint():
    # Mock data để test độc lập với mạng
    mock_articles = [
        {
            "id": "vnexpress-0-12345",
            "title": "Thị trường bất động sản ghi nhận tín hiệu tích cực",
            "link": "https://vnexpress.net/bat-dong-san/test-1",
            "image_url": "https://i1-vnexpress.vnecdn.net/test.jpg",
            "source": "VnExpress",
            "source_name": "VnExpress Bất động sản",
            "pub_date": "Thu, 20 Aug 2026 09:00:00 +0700",
            "summary": "Nguồn cung căn hộ tăng nhẹ trong quý vừa qua...",
        },
        {
            "id": "cafef-1-67890",
            "title": "Giá căn hộ khu Đông tiếp tục ổn định",
            "link": "https://cafef.vn/bat-dong-san/test-2",
            "image_url": "https://cafefcdn.com/test.jpg",
            "source": "CafeF",
            "source_name": "CafeF Bất động sản",
            "pub_date": "Thu, 20 Aug 2026 10:00:00 +0700",
            "summary": "Nhiều dự án bàn giao đúng tiến độ thu hút cư dân...",
        },
    ]

    with patch("app.routers.news.get_real_estate_news_async", new_callable=AsyncMock, return_value=mock_articles):
        response = client.get("/api/news?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["title"] == "Thị trường bất động sản ghi nhận tín hiệu tích cực"
        assert data["items"][0]["image_url"] == "https://i1-vnexpress.vnecdn.net/test.jpg"
        assert data["items"][0]["source"] == "VnExpress"
