from fastapi.testclient import TestClient

from app.core.config import settings

SCHOOLS_URL = f"{settings.API_V1_STR}/schools"


def test_public_school_list_is_seeded_and_sorted_by_name(client: TestClient) -> None:
    response = client.get(SCHOOLS_URL)

    assert response.status_code == 200
    schools = response.json()
    # 初始資料：教育部大專校院名錄 115 學年度，139 所
    assert len(schools) == 139
    names = [school["name"] for school in schools]
    # 依碼位排序（資料庫以 COLLATE "C" 排序，與 Python 的 sorted 相同）
    assert names == sorted(names)
    assert "國立臺灣大學" in names
    assert set(schools[0]) == {"id", "name"}
