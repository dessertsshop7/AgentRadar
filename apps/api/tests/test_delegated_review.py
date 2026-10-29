"""委托 AI 审核：真实独立 PostgreSQL，外部 HTTP 数据为明确测试夹具。"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_sync import GitHubScene, run, service_context

from app.db.models import Asset, AssetVersion
from app.ingestion.maintenance import ContentDraft, publish_version, save_draft

pytestmark = pytest.mark.integration
AUTHORIZATION = "test-fixture:explicit-user-delegation"


async def seed_draft(service):
    await service.run("github", queries=["fixture"])
    async with service.sessions.begin() as session:
        asset = await session.scalar(select(Asset))
        version = await save_draft(
            session,
            asset.id,
            ContentDraft(
                summary_zh="测试资料：团队文档问答工具",
                categories=["knowledge"],
                origin="assistant_draft",
            ),
            expected_source_hash=asset.current_source_hash,
        )
        return asset.id, version.id, asset.current_source_hash


def test_ai_reviewer_cannot_be_recorded_as_human_review(pg, database_url):
    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            _, version_id, _ = await seed_draft(service)
            async with service.sessions.begin() as session:
                with pytest.raises(ValueError, match="AI"):
                    await publish_version(session, version_id, reviewer="ai:codex", confirmed=True)

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(Asset.published_version_id)) is None


def test_delegated_ai_publish_preserves_origin_and_exposes_truthful_actor(
    pg, database_url, asset_client
):
    async def scenario():
        from app.cli import execute, parser

        async with service_context(database_url, GitHubScene()) as service:
            _, version_id, _ = await seed_draft(service)
            args = parser().parse_args(
                [
                    "publish",
                    "--version",
                    str(version_id),
                    "--reviewer",
                    "ai:codex",
                    "--confirm-delegated-ai-review",
                    "--authorization-ref",
                    AUTHORIZATION,
                    "--note",
                    "测试资料核对完成；未安装验证",
                ]
            )
            assert (await execute(args))["status"] == "approved"

    run(scenario())
    item = asset_client.get("/api/v1/assets").json()["items"][0]
    assert item["origin"] == "assistant_draft"
    assert item["review"]["actor_type"] == "delegated_ai"
    assert item["review"]["reviewed_by"] == "ai:codex"
    with Session(pg) as session:
        version = session.get(AssetVersion, session.scalar(select(Asset.published_version_id)))
        assert version.raw_data["review"]["authorization_ref"] == AUTHORIZATION
        assert version.review_note == "测试资料核对完成；未安装验证"


@pytest.mark.parametrize(
    ("reviewer", "confirmed", "authorization"),
    [
        ("ai:codex", False, AUTHORIZATION),
        ("ai:codex", True, None),
        ("人类姓名", True, AUTHORIZATION),
    ],
)
def test_delegated_review_requires_explicit_confirmation_and_ai_identity(
    pg, database_url, reviewer, confirmed, authorization
):
    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            _, version_id, _ = await seed_draft(service)
            async with service.sessions.begin() as session:
                with pytest.raises(ValueError):
                    await publish_version(
                        session,
                        version_id,
                        reviewer=reviewer,
                        confirmed=confirmed,
                        review_actor="delegated_ai",
                        authorization_ref=authorization,
                    )

    run(scenario())
    with Session(pg) as session:
        assert session.scalar(select(Asset.published_version_id)) is None


def test_ai_authorization_does_not_bypass_changed_source(pg, database_url):
    async def scenario():
        scene = GitHubScene()
        async with service_context(database_url, scene) as service:
            _, version_id, _ = await seed_draft(service)
            scene.body += "\nnew source facts"
            scene.etag = '"new-source"'
            scene.metadata["pushed_at"] = "2026-10-28T00:00:00Z"
            await service.run("github", queries=["fixture"])
            async with service.sessions.begin() as session:
                with pytest.raises(ValueError, match="来源已变化"):
                    await publish_version(
                        session,
                        version_id,
                        reviewer="ai:codex",
                        confirmed=True,
                        review_actor="delegated_ai",
                        authorization_ref=AUTHORIZATION,
                    )

    run(scenario())


def test_deferral_is_a_separate_idempotent_ai_record_and_stays_unpublished(
    pg, database_url, asset_client
):
    from app.ingestion.maintenance import defer_asset

    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            asset_id, _, digest = await seed_draft(service)
            async with service.sessions.begin() as session:
                first = await defer_asset(
                    session,
                    asset_id,
                    expected_source_hash=digest,
                    reviewer="ai:codex",
                    confirmed=True,
                    review_actor="delegated_ai",
                    authorization_ref=AUTHORIZATION,
                    note="测试依据：教程资源暂不计入软件目录",
                )
                second = await defer_asset(
                    session,
                    asset_id,
                    expected_source_hash=digest,
                    reviewer="ai:codex",
                    confirmed=True,
                    review_actor="delegated_ai",
                    authorization_ref=AUTHORIZATION,
                    note="测试依据：教程资源暂不计入软件目录",
                )
                assert first.id == second.id

    run(scenario())
    assert asset_client.get("/api/v1/assets").json()["total"] == 0
    with Session(pg) as session:
        decision = session.scalar(select(AssetVersion).where(AssetVersion.status == "rejected"))
        assert decision.content_origin == "assistant_draft"
        assert decision.raw_data["review"]["actor_type"] == "delegated_ai"
        assert decision.raw_data["review"]["decision"] == "deferred"
        assert session.scalar(select(Asset.review_state)) == "pending"
        assert (
            session.scalar(
                select(func.count())
                .select_from(AssetVersion)
                .where(AssetVersion.content_origin == "source_metadata")
            )
            == 1
        )


def test_new_human_review_exposes_human_actor(pg, database_url, asset_client):
    async def scenario():
        async with service_context(database_url, GitHubScene()) as service:
            _, version_id, _ = await seed_draft(service)
            async with service.sessions.begin() as session:
                await publish_version(session, version_id, reviewer="测试人类", confirmed=True)

    run(scenario())
    assert asset_client.get("/api/v1/assets").json()["items"][0]["review"]["actor_type"] == "human"
