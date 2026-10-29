"""真实 PostgreSQL + 外部 HTTP 替身；时间历史仅为测试夹具。"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_providers import repository_payload

from app.core.config import Settings
from app.db.session import create_database_engine

pytestmark = pytest.mark.integration


def run(coroutine):
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coroutine)


class GitHubScene:
    def __init__(self):
        self.metadata = repository_payload()
        self.body = "# Fixture\nRAG framework documentation"
        self.etag = '"first"'
        self.metadata_status = 200
        self.gate = self.entered = None

    async def respond(self, request):
        if request.url.path == "/search/repositories":
            if self.gate:
                self.entered.set()
                await self.gate.wait()
            return httpx.Response(
                200, json={"total_count": 1, "incomplete_results": False, "items": [self.metadata]}
            )
        if request.url.path.endswith("/readme"):
            if request.headers.get("if-none-match") == self.etag:
                return httpx.Response(304)
            return httpx.Response(200, text=self.body, headers={"etag": self.etag})
        return httpx.Response(self.metadata_status, json=self.metadata)


@asynccontextmanager
async def service_context(database_url, scene, clock=None):
    from app.ingestion.providers import GitHubRepositoryAdapter
    from app.ingestion.sync import SyncService

    settings = Settings(_env_file=None, database_url=database_url, github_token="test-only")
    engine = create_database_engine(settings)
    async with httpx.AsyncClient(
        base_url="https://api.github.com", transport=httpx.MockTransport(scene.respond)
    ) as client:
        service = SyncService(engine, settings, github=GitHubRepositoryAdapter(client), clock=clock)
        try:
            yield service
        finally:
            await engine.dispose()


def test_sync_repetition_is_idempotent_but_keeps_distinct_job_observations(pg, database_url):
    from app.db.models import (
        Asset,
        AssetRepository,
        AssetVersion,
        Repository,
        RepositoryDocument,
        RepositorySnapshot,
    )

    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            assert (await service.run("github", queries=["fixture"]))["status"] == "succeeded"
            assert (await service.run("github", queries=["fixture"]))["status"] == "succeeded"

    run(scenario())
    with Session(pg) as session:
        for model in (Asset, Repository, AssetRepository, RepositoryDocument, AssetVersion):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        assert session.scalar(select(func.count()).select_from(RepositorySnapshot)) == 2


def test_304_and_same_content_hash_do_not_make_versions(pg, database_url):
    from app.db.models import AssetVersion, RepositoryDocument

    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            scene.metadata["pushed_at"] = "2026-10-18T00:00:00Z"
            result = await service.run("github", queries=["fixture"])
            assert result["counts"]["readmes_unchanged"] == 1
            scene.metadata["pushed_at"] = "2026-10-18T01:00:00Z"
            scene.etag = '"different-etag-same-body"'
            result = await service.run("github", queries=["fixture"])
            assert result["counts"]["readmes_unchanged"] == 1

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(RepositoryDocument)) == 1
        assert session.scalar(select(func.count()).select_from(AssetVersion)) == 1


def test_source_change_keeps_approved_content_and_adds_unpublished_draft(
    pg, database_url, asset_client
):
    from app.db.models import Asset, AssetVersion
    from app.ingestion.maintenance import ContentDraft, publish_version, save_draft

    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions() as session:
                asset = await session.scalar(select(Asset))
                draft = await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="测试夹具：团队知识检索框架", categories=["knowledge"]),
                )
                await publish_version(session, draft.id, reviewer="自动化测试夹具", confirmed=True)
                await session.commit()
            scene.metadata["pushed_at"] = "2026-10-18T01:00:00Z"
            scene.body += "\nchanged README"
            scene.etag = '"changed"'
            await service.run("github", queries=["fixture"])

    run(scenario())
    with Session(pg) as session:
        asset = session.scalar(select(Asset))
        assert asset.review_state == "needs_review"
        assert (
            session.get(AssetVersion, asset.published_version_id).summary_zh
            == "测试夹具：团队知识检索框架"
        )
        assert session.scalar(select(func.count()).select_from(AssetVersion)) == 3
    item = asset_client.get("/api/v1/assets").json()["items"][0]
    assert item["summary_zh"] == "测试夹具：团队知识检索框架" and item["needs_review"]


def test_database_mutex_rejects_concurrent_sync_and_health_stays_available(
    pg, database_url, asset_client
):
    async def scenario():
        scene = GitHubScene()
        scene.gate, scene.entered = asyncio.Event(), asyncio.Event()
        async with service_context(database_url, scene) as service:
            first = asyncio.create_task(service.run("github", queries=["fixture"]))
            await scene.entered.wait()
            assert (await service.run("github", queries=["fixture"]))["status"] == "locked"
            assert asset_client.get("/api/v1/health").status_code == 200
            scene.gate.set()
            assert (await first)["status"] == "succeeded"

    run(scenario())


def test_catch_up_runs_once_not_once_per_missed_interval_and_recovers_orphan(pg, database_url):
    from app.db.models import SyncJob

    instant = [datetime(2026, 10, 18, tzinfo=UTC)]

    async def scenario():
        async with service_context(
            database_url, GitHubScene(), clock=lambda: instant[0]
        ) as service:
            assert (await service.run("github", queries=["fixture"], due_only=True))[
                "status"
            ] == "succeeded"
            assert (await service.run("github", queries=["fixture"], due_only=True))[
                "status"
            ] == "not_due"
            async with service.sessions() as session:
                orphan = SyncJob(source_id="github", status="running", started_at=instant[0])
                session.add(orphan)
                await session.commit()
            instant[0] += timedelta(days=10)
            assert (await service.run("github", queries=["fixture"], due_only=True))[
                "status"
            ] == "succeeded"
            assert (await service.run("github", queries=["fixture"], due_only=True))[
                "status"
            ] == "not_due"

    run(scenario())
    with Session(pg) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(SyncJob).where(SyncJob.status == "succeeded")
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count()).select_from(SyncJob).where(SyncJob.status == "interrupted")
            )
            == 1
        )


def test_inaccessible_repository_is_unverified_and_partial_does_not_advance_success(
    pg, database_url
):
    from app.db.models import Repository, Source, SyncError

    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions() as session:
                previous = (await session.get(Source, "github")).last_success_at
            scene.metadata_status = 404
            scene.metadata["pushed_at"] = "2026-10-18T02:00:00Z"
            assert (await service.run("github", queries=["fixture"]))["status"] == "partial"
            async with service.sessions() as session:
                assert (await session.get(Source, "github")).last_success_at == previous

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(Repository)).availability == "unverified"
        assert session.scalar(select(SyncError)).code == "NOT_FOUND_OR_INACCESSIBLE"


def test_renamed_repository_keeps_identity_and_slug(pg, database_url):
    from app.db.models import Asset, Repository

    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            scene.metadata["full_name"] = "renamed/project"
            scene.metadata["html_url"] = "https://github.com/renamed/project"
            await service.run("github", queries=["fixture"])

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(Repository)) == 1
        assert session.scalar(select(Repository)).full_name == "renamed/project"
        assert session.scalar(select(Asset)).slug == "gh-42"


def test_publish_requires_explicit_human_confirmation_and_chinese_content(pg, database_url):
    from app.db.models import Asset, AssetVersion
    from app.ingestion.maintenance import ContentDraft, publish_version, save_draft

    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions() as session:
                raw = await session.scalar(select(AssetVersion))
                with pytest.raises(ValueError):
                    await publish_version(session, raw.id, reviewer="测试夹具", confirmed=True)
                asset = await session.scalar(select(Asset))
                draft = await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="测试中文内容，待人工审核", categories=["knowledge"]),
                )
                with pytest.raises(ValueError, match="人工审核确认"):
                    await publish_version(session, draft.id, reviewer="测试夹具", confirmed=False)
                await session.rollback()

    run(scenario())


def test_one_asset_can_link_multiple_repositories_without_duplicate_listing(pg, asset_client):
    from test_assets import seed_catalog

    from app.db.models import AssetRepository, Repository

    ids = seed_catalog(pg)
    from uuid import UUID

    with Session(pg) as session:
        repo = Repository(
            source_id="github",
            external_id="99",
            full_name="test/secondary",
            canonical_url="https://github.com/test/secondary",
        )
        session.add(repo)
        session.flush()
        session.add(AssetRepository(asset_id=UUID(ids["knowledge-fixture"]), repository_id=repo.id))
        session.commit()
    result = asset_client.get("/api/v1/assets").json()
    assert result["total"] == 2
    assert len(result["items"][0]["sources"]) == 2


def test_source_reversion_reuses_history_and_restores_matching_approved_version(pg, database_url):
    from app.db.models import Asset, RepositoryDocument
    from app.ingestion.maintenance import ContentDraft, current_source, publish_version, save_draft

    async def scenario():
        scene = GitHubScene()
        original = scene.body
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions.begin() as session:
                asset = await session.scalar(select(Asset))
                first_source = (await current_source(session, asset)).source_hash
                draft = await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="已审核的测试中文知识库", categories=["knowledge"]),
                )
                await publish_version(session, draft.id, reviewer="测试夹具", confirmed=True)
            scene.body, scene.etag, scene.metadata["pushed_at"] = (
                "changed",
                '"second"',
                "2026-10-18T01:00:00Z",
            )
            await service.run("github", queries=["fixture"])
            scene.body, scene.etag, scene.metadata["pushed_at"] = (
                original,
                '"third"',
                "2026-10-18T02:00:00Z",
            )
            await service.run("github", queries=["fixture"])
            async with service.sessions() as session:
                asset = await session.scalar(select(Asset))
                assert (await current_source(session, asset)).source_hash == first_source
                assert asset.review_state == "approved"

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(func.count()).select_from(RepositoryDocument)) == 2


def test_draft_category_changes_cannot_leak_into_published_filters(pg, database_url, asset_client):
    from app.db.models import Asset
    from app.ingestion.maintenance import ContentDraft, publish_version, save_draft

    async def scenario():
        scene = GitHubScene()
        scene.metadata["description"], scene.metadata["topics"] = "RAG", ["rag"]
        async with service_context(database_url, scene) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions.begin() as session:
                asset = await session.scalar(select(Asset))
                draft = await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="已审知识检索测试说明", categories=["knowledge"]),
                )
                await publish_version(session, draft.id, reviewer="测试夹具", confirmed=True)
            async with service.sessions.begin() as session:
                asset = await session.scalar(select(Asset))
                await save_draft(
                    session,
                    asset.id,
                    ContentDraft(summary_zh="尚未审核的新中文草稿", categories=["framework"]),
                )

    run(scenario())
    assert asset_client.get("/api/v1/assets?category=framework").json()["total"] == 0
    assert asset_client.get("/api/v1/assets").json()["items"][0]["categories"] == ["knowledge"]
    assert asset_client.get("/api/v1/categories").json()["items"] == [
        {"id": "knowledge", "label": "知识管理/RAG", "count": 1}
    ]


def test_unexpected_failure_persists_safe_error_and_does_not_stay_running(pg, database_url):
    from app.db.models import SyncError, SyncJob

    async def scenario():
        scene = GitHubScene()

        async def fail(request):
            raise RuntimeError("secret-sentinel")

        scene.respond = fail
        async with service_context(database_url, scene) as service:
            with pytest.raises(RuntimeError):
                await service.run("github", queries=["fixture"])

    run(scenario())
    with Session(pg) as session:
        job = session.scalar(select(SyncJob))
        assert job.status == "failed" and job.counts["errors"] == 1
        error = session.scalar(select(SyncError))
        assert error.code == "INTERNAL_ERROR" and "secret-sentinel" not in error.message


def test_review_export_can_select_real_readme_candidates_without_publishing(
    pg, database_url, monkeypatch, tmp_path
):
    import argparse
    import json

    from app.cli import execute
    from app.db.models import Asset, AssetVersion

    monkeypatch.setenv("DATABASE_URL", database_url)
    output = tmp_path / "review.json"

    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            await service.run("github", queries=["fixture"])
            async with service.sessions.begin() as session:
                asset = Asset(
                    source_id="mcp",
                    external_id="org.fixture/no-repo",
                    slug="registry-fixture",
                    name="Registry fixture",
                    asset_type="mcp",
                    current_source_hash="b" * 64,
                )
                session.add(asset)
                await session.flush()
                session.add(
                    AssetVersion(
                        asset_id=asset.id,
                        source_hash="b" * 64,
                        content_hash="c" * 64,
                        source_url="https://registry.modelcontextprotocol.io/v0.1/servers/example",
                        raw_data={"server": {"description": "Test fixture"}},
                    )
                )
            result = await execute(
                argparse.Namespace(command="export-review", output=output, with_readme=True)
            )
            assert result["pending_items"] == 1 and result["published_by_this_command"] == 0

    run(scenario())
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["items"][0]["has_readme"] and data["counts"]["published_assets"] == 0


def test_registry_checkpoint_replays_interrupted_batch_without_skipping_assets(pg, database_url):
    from app.db.models import Asset, Source
    from app.ingestion.providers import MCPRegistryAdapter
    from app.ingestion.sync import SyncService

    async def scenario():
        requests = []

        def respond(request):
            cursor = request.url.params.get("cursor")
            requests.append(cursor)
            names = ["org.example/c"] if cursor else ["org.example/a", "org.example/b"]
            return httpx.Response(
                200,
                json={
                    "servers": [
                        {"server": {"name": name, "version": "1", "description": "Test fixture"}}
                        for name in names
                    ],
                    "metadata": {} if cursor else {"nextCursor": "next-batch"},
                },
            )

        settings = Settings(_env_file=None, database_url=database_url)
        engine = create_database_engine(settings)
        async with httpx.AsyncClient(
            base_url="https://registry.modelcontextprotocol.io",
            transport=httpx.MockTransport(respond),
        ) as client:
            service = SyncService(engine, settings, mcp=MCPRegistryAdapter(client))
            entered, gate = asyncio.Event(), asyncio.Event()
            original = service._source_version

            async def pause_second(session, asset, *args, **kwargs):
                if asset.external_id == "org.example/b":
                    entered.set()
                    await gate.wait()
                return await original(session, asset, *args, **kwargs)

            service._source_version = pause_second
            task = asyncio.create_task(service.run("mcp", max_records=2))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            service._source_version = original
            assert (await service.run("mcp", max_records=2))["status"] == "partial"
            assert requests[:2] == [None, None]
            async with service.sessions() as session:
                assert (await session.get(Source, "mcp")).last_success_at is None
            assert (await service.run("mcp", max_records=2))["status"] == "succeeded"
        await engine.dispose()

    run(scenario())
    with Session(pg) as session:
        assert set(session.scalars(select(Asset.external_id))) == {
            "org.example/a",
            "org.example/b",
            "org.example/c",
        }
