"""审查缺陷回归：外部 HTTP 为替身，集成用例连接独立 PostgreSQL。"""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_assets import seed_catalog
from test_providers import repository_payload
from test_sync import GitHubScene, run, service_context


@pytest.mark.integration
def test_default_plan_resumes_inside_query_across_service_restarts(pg, database_url, monkeypatch):
    monkeypatch.setattr("app.ingestion.sync.default_queries", lambda now: ["first", "second"])

    class Scene(GitHubScene):
        async def respond(self, request):
            if request.url.path == "/search/repositories":
                identities = [1, 2] if request.url.params["q"] == "first" else [3]
                return httpx.Response(
                    200,
                    json={
                        "total_count": len(identities),
                        "items": [repository_payload(n) for n in identities],
                    },
                )
            return await super().respond(request)

    async def scenario():
        for index in range(3):
            async with service_context(database_url, Scene()) as service:
                await service.run("github", max_records=1, readme_limit=0)
                if index == 0:
                    # 无关手工查询不能重置默认计划检查点。
                    await service.run("github", queries=["second"], max_records=1, readme_limit=0)

    run(scenario())
    from app.db.models import Repository, Source

    with Session(pg) as session:
        assert set(session.scalars(select(Repository.external_id))) == {"1", "2", "3"}
        assert session.get(Source, "github").last_success_at is not None


@pytest.mark.integration
def test_missing_readme_is_checked_once_and_budget_moves_to_unchecked_repo(pg, database_url):
    reads = []

    class Scene(GitHubScene):
        async def respond(self, request):
            if request.url.path == "/search/repositories":
                return httpx.Response(
                    200,
                    json={
                        "total_count": 2,
                        "items": [repository_payload(n, f"fixture/repo{n}") for n in (1, 2)],
                    },
                )
            if request.url.path.endswith("/readme"):
                reads.append(request.url.path)
                return httpx.Response(404)
            n = int(request.url.path.rsplit("repo", 1)[1])
            return httpx.Response(200, json=repository_payload(n, f"fixture/repo{n}"))

    async def scenario():
        async with service_context(database_url, Scene()) as service:
            for _ in range(3):
                await service.run("github", queries=["fixture"], readme_limit=1)

    run(scenario())
    assert reads == ["/repos/fixture/repo1/readme", "/repos/fixture/repo2/readme"]


@pytest.mark.integration
def test_license_change_with_same_readme_requires_review_and_is_idempotent(pg, database_url):
    from app.db.models import Asset, AssetVersion
    from app.ingestion.maintenance import ContentDraft, publish_version, save_draft

    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions.begin() as session:
                asset = await session.scalar(select(Asset))
                draft = await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="中文许可说明测试", categories=["knowledge"]),
                )
                await publish_version(session, draft.id, reviewer="测试夹具", confirmed=True)
            scene.metadata["license"] = {"spdx_id": "AGPL-3.0"}
            for _ in range(2):
                await service.run("github", queries=["fixture"])
            async with service.sessions() as session:
                asset = await session.scalar(select(Asset))
                assert asset.review_state == "needs_review"
                assert (
                    asset.current_source_hash
                    != (await session.get(AssetVersion, asset.published_version_id)).source_hash
                )
            scene.metadata["license"] = {"spdx_id": "MIT"}
            await service.run("github", queries=["fixture"])

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(Asset.review_state)) == "approved"
        assert len(session.scalars(select(AssetVersion)).all()) == 3


def test_trend_weights_change_score_and_record_formula_version():
    from app.ingestion.rules import calculate_trend

    now = datetime(2026, 10, 29, tzinfo=UTC)
    result = calculate_trend(
        [(now, 100)],
        now,
        now,
        True,
        weights={"growth": 0, "activity": 0, "freshness": 0, "quality": 1},
        formula_version="quality-v1",
    )
    assert result["score"] == 100
    assert result["formula_version"] == "quality-v1"
    assert result["components"]["weights"]["quality"] == 1


def test_custom_weights_require_new_version_and_valid_normalization():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x:x@localhost/test",
            trend_weights={"growth": 0, "activity": 0, "freshness": 0, "quality": 1},
        )


@pytest.mark.parametrize(
    "weights",
    [
        {"quality": 1},
        {"growth": -1, "activity": 1, "freshness": 0, "quality": 1},
        {"growth": float("nan"), "activity": 0, "freshness": 0, "quality": 1},
        {"growth": 1, "activity": 1, "freshness": 1, "quality": 1},
    ],
)
def test_invalid_trend_rules_are_rejected(weights):
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://x:x@localhost/test",
            trend_formula_version="fixture-v2",
            trend_weights=weights,
        )


def test_registry_empty_pages_have_a_total_page_bound():
    from app.ingestion.providers import MCPRegistryAdapter, ProviderError

    async def scenario():
        calls = 0

        def respond(request):
            nonlocal calls
            calls += 1
            if calls > 101:
                raise AssertionError("分页未按上限结束")
            return httpx.Response(200, json={"servers": [], "metadata": {"nextCursor": str(calls)}})

        async with httpx.AsyncClient(
            base_url="https://registry.modelcontextprotocol.io",
            transport=httpx.MockTransport(respond),
        ) as client:
            with pytest.raises(ProviderError, match="PAGINATION_LIMIT"):
                await MCPRegistryAdapter(client).discover(limit=1)

    asyncio.run(scenario())


def test_registry_total_timeout_is_reported_as_a_safe_error(monkeypatch):
    from app.ingestion.providers import MCPRegistryAdapter, ProviderError

    original_timeout = asyncio.timeout
    monkeypatch.setattr(
        "app.ingestion.providers.asyncio.timeout",
        lambda duration: original_timeout(0.001 if duration == 60 else duration),
    )

    async def scenario():
        async def respond(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json={"servers": [], "metadata": {}})

        async with httpx.AsyncClient(
            base_url="https://registry.modelcontextprotocol.io",
            transport=httpx.MockTransport(respond),
        ) as client:
            with pytest.raises(ProviderError, match="PAGINATION_TIMEOUT"):
                await MCPRegistryAdapter(client).discover()

    asyncio.run(scenario())


@pytest.mark.integration
def test_withdraw_missing_source_is_a_readable_validation_error(pg, database_url):
    from app.db.models import Asset, Source
    from app.ingestion.maintenance import withdraw_asset

    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            async with service.sessions.begin() as session:
                session.add(Source(id="github", label="test", base_url="https://api.github.com"))
                await session.flush()
                asset = Asset(
                    source_id="github", external_id="missing", slug="missing", name="missing"
                )
                session.add(asset)
                await session.flush()
                with pytest.raises(ValueError, match="来源"):
                    await withdraw_asset(
                        session, asset.id, reviewer="测试", confirmed=True, note="测试"
                    )

    run(scenario())


@pytest.mark.integration
def test_kind_maintenance_filters_and_public_repository_fields(pg, asset_client):
    from app.db.models import Asset

    ids = seed_catalog(pg)  # 该夹具本身已包含同一仓库关联多个资产。
    with Session(pg) as session:
        asset = session.scalar(select(Asset).where(Asset.slug == "operations-fixture"))
        asset.asset_type = "mcp"
        asset.review_state = "needs_review"
        session.commit()
    result = asset_client.get(
        "/api/v1/assets", params={"kind": "mcp", "maintenance": "needs_review"}
    )
    assert result.status_code == 200
    assert [item["id"] for item in result.json()["items"]] == [ids["operations-fixture"]]
    source = result.json()["items"][0]["sources"][0]
    assert source["pushed_at"] and source["stars"] == 12 and source["availability"] == "active"
    assert asset_client.get("/api/v1/assets", params={"kind": "invalid"}).status_code == 422
    assert asset_client.get("/api/v1/categories").headers["cache-control"] == "public, max-age=30"
    assert asset_client.get("/api/v1/trending").headers["cache-control"] == "public, max-age=30"
    assert asset_client.get("/api/v1/trending", params={"kind": "invalid"}).status_code == 422


@pytest.mark.integration
def test_updated_sort_uses_repository_push_and_shared_repo_keeps_distinct_assets(pg, asset_client):
    from datetime import timedelta

    from app.db.models import Asset, AssetRepository

    seed_catalog(pg)
    with Session(pg) as session:
        asset = session.scalar(select(Asset).where(Asset.slug == "operations-fixture"))
        asset.collected_at = datetime.now(UTC) + timedelta(days=1)
        assert len(set(session.scalars(select(AssetRepository.repository_id)))) == 1
        session.commit()
    items = asset_client.get("/api/v1/assets", params={"sort": "updated"}).json()["items"]
    assert [item["slug"] for item in items] == ["knowledge-fixture", "operations-fixture"]


def test_github_window_resumes_within_page_without_skipping_items():
    from app.ingestion.providers import GitHubRepositoryAdapter

    async def scenario():
        def respond(request):
            page = int(request.url.params["page"])
            ids = range((page - 1) * 100 + 1, min(page * 100, 103) + 1)
            return httpx.Response(
                200, json={"total_count": 103, "items": [repository_payload(n) for n in ids]}
            )

        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(respond)
        ) as client:
            adapter = GitHubRepositoryAdapter(client)
            a = await adapter.discover("fixture", limit=73, offset=0)
            b = await adapter.discover("fixture", limit=73, offset=a.next_offset)
            assert [row["id"] for row in a.records + b.records] == list(range(1, 104))
            assert b.next_offset is None

    asyncio.run(scenario())


@pytest.mark.integration
def test_disappeared_readme_stays_hidden_when_negative_check_is_cached(
    pg, database_url, asset_client
):
    from test_delegated_review import seed_draft

    from app.ingestion.maintenance import publish_version

    class Scene(GitHubScene):
        missing = False

        async def respond(self, request):
            if self.missing and request.url.path.endswith("/readme"):
                return httpx.Response(404)
            return await super().respond(request)

    async def scenario():
        from datetime import timedelta

        instant = [datetime(2026, 10, 29, tzinfo=UTC)]
        scene = Scene()
        async with service_context(database_url, scene, clock=lambda: instant[0]) as service:
            _, version_id, _ = await seed_draft(service)
            async with service.sessions.begin() as session:
                await publish_version(session, version_id, reviewer="测试", confirmed=True)
            scene.missing = True
            scene.metadata["pushed_at"] = "2026-10-29T00:00:00Z"
            for _ in range(2):
                await service.run("github", queries=["fixture"])
                assert asset_client.get("/api/v1/assets").json()["total"] == 0
            scene.missing = False
            instant[0] += timedelta(days=2)
            await service.run("github", queries=["fixture"])
            assert asset_client.get("/api/v1/assets").json()["total"] == 1

    run(scenario())
