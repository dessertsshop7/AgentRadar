"""P02 查询与发布隔离：连接独立真实 PostgreSQL，内容均为测试夹具。"""

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def seed_catalog(pg):
    from app.db.models import (
        Asset,
        AssetCategory,
        AssetCategoryLink,
        AssetRepository,
        AssetVersion,
        Repository,
        Source,
    )

    with Session(pg) as session:
        session.add(Source(id="github", label="GitHub", base_url="https://api.github.com"))
        session.add(AssetCategory(id="knowledge", label="知识管理/RAG"))
        session.flush()
        repo = Repository(
            source_id="github",
            external_id="42",
            full_name="test/real-fixture",
            canonical_url="https://github.com/test/real-fixture",
            stars=12,
            pushed_at=datetime.now(UTC),
        )
        session.add(repo)
        session.flush()
        ids = {}
        for slug, summary, status in [
            ("knowledge-fixture", "团队知识库问答，100% 本地资料", "approved"),
            ("operations-fixture", "运营内容排期与文档管理", "approved"),
            ("secret-fixture", "秘密草稿知识库", "pending"),
            ("withdrawn-fixture", "已撤下的知识库", "withdrawn"),
        ]:
            asset = Asset(
                source_id="github",
                external_id=slug,
                slug=slug,
                name=slug,
                asset_type="tool",
                review_state=status,
            )
            session.add(asset)
            session.flush()
            version = AssetVersion(
                asset_id=asset.id,
                source_hash="a" * 64,
                content_hash=slug,
                summary_zh=summary,
                difficulty="developer",
                tags=["中文标签"],
                categories=["knowledge"],
                scenarios=["文档管理"],
                content_origin="human",
                status="approved" if status == "approved" else "draft",
                reviewed_by="测试审核夹具" if status == "approved" else None,
                reviewed_at=datetime.now(UTC) if status == "approved" else None,
            )
            session.add(version)
            session.flush()
            if status == "approved":
                asset.published_version_id = version.id
            session.add(AssetRepository(asset_id=asset.id, repository_id=repo.id, is_primary=True))
            session.add(
                AssetCategoryLink(asset_id=asset.id, category_id="knowledge", evidence="测试规则")
            )
            ids[slug] = str(asset.id)
        session.commit()
        return ids


def test_empty_catalog_is_a_successful_real_database_query(asset_client):
    response = asset_client.get("/api/v1/assets")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["total"] == 0
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_p02_migration_contains_distinct_entities_and_relations(pg):
    assert {
        "sources",
        "repositories",
        "assets",
        "asset_repositories",
        "asset_versions",
        "asset_categories",
        "repository_snapshots",
        "sync_jobs",
        "sync_errors",
    } <= set(inspect(pg).get_table_names())


def test_public_catalog_chinese_search_and_literal_wildcards(asset_client, pg):
    seed_catalog(pg)
    response = asset_client.get(
        "/api/v1/assets", params={"q": "知识库", "category": "knowledge", "difficulty": "developer"}
    )
    assert response.status_code == 200
    assert [item["slug"] for item in response.json()["items"]] == ["knowledge-fixture"]
    assert response.json()["items"][0]["cost"] == "unknown"
    assert asset_client.get("/api/v1/assets", params={"q": "100%"}).json()["total"] == 1
    assert asset_client.get("/api/v1/assets", params={"q": "不存在的中文词"}).json()["total"] == 0
    assert asset_client.get("/api/v1/assets", params={"q": "_"}).json()["total"] == 0
    assert asset_client.get("/api/v1/assets", params={"q": "文档管理"}).json()["total"] == 2
    samples = []
    for keyword, expected in [
        ("知识库", 1),
        ("中文标签", 2),
        ("不存在的中文词", 0),
        ("100%", 1),
        ("_", 0),
    ]:
        started = perf_counter()
        result = asset_client.get("/api/v1/assets", params={"q": keyword})
        elapsed = (perf_counter() - started) * 1000
        assert result.json()["total"] == expected
        samples.append({"q": keyword, "hits": expected, "http_ms": round(elapsed, 3)})
    output = Path("artifacts/p02/chinese-search.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "data": "独立真实 PostgreSQL；4 条合成测试资产，2 条已审夹具；不代表真实发布池",
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_drafts_and_withdrawn_assets_do_not_leak_through_any_public_read(asset_client, pg):
    ids = seed_catalog(pg)
    assert asset_client.get("/api/v1/assets").json()["total"] == 2
    for slug in ("secret-fixture", "withdrawn-fixture"):
        for key in (slug, ids[slug]):
            response = asset_client.get(f"/api/v1/assets/{key}")
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "HTTP_404"
    categories = asset_client.get("/api/v1/categories").json()["items"]
    assert categories == [{"id": "knowledge", "label": "知识管理/RAG", "count": 2}]
    assert asset_client.get("/api/v1/trending").json()["items"] == []


def test_pagination_is_stable_and_detail_resolves_id_or_slug(asset_client, pg):
    ids = seed_catalog(pg)
    first = asset_client.get("/api/v1/assets?page_size=1").json()
    second = asset_client.get("/api/v1/assets?page_size=1&page=2").json()
    assert first["total"] == 2
    assert first["items"][0]["slug"] == "knowledge-fixture"
    assert second["items"][0]["slug"] == "operations-fixture"
    for key in ("knowledge-fixture", ids["knowledge-fixture"]):
        detail = asset_client.get(f"/api/v1/assets/{key}").json()
        assert detail["item"]["summary_zh"] == "团队知识库问答，100% 本地资料"
        assert detail["item"]["review"]["reviewed_by"] == "测试审核夹具"
        assert detail["item"]["sources"][0]["url"].startswith("https://github.com/")


@pytest.mark.parametrize(
    "query", ["page=0", "page_size=51", "difficulty=magical", "category=invalid", "q=" + "a" * 101]
)
def test_invalid_filters_follow_the_p00_error_contract(asset_client, query):
    response = asset_client.get("/api/v1/assets?" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
