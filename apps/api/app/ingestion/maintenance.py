"""受控维护事务；区分人工审核与用户明确委托的 AI 审核。"""

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Asset, AssetCategoryLink, AssetRepository, AssetVersion, Repository
from app.ingestion.rules import content_hash


class ContentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    summary_zh: str = Field(min_length=5, max_length=1500)
    name_zh: str | None = Field(default=None, max_length=300)
    description_zh: str | None = Field(default=None, max_length=10000)
    difficulty: Literal["unknown", "beginner", "visual", "developer"] = "unknown"
    cost: str = Field(default="unknown", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=20)
    scenarios: list[str] = Field(default_factory=list, max_length=12)
    requirements: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    categories: list[Literal["knowledge", "agent-workflow", "mcp-integration", "framework"]] = (
        Field(min_length=1, max_length=4)
    )
    origin: Literal["human", "assistant_draft"] = "human"


async def current_source(session, asset):
    return await session.scalar(
        select(AssetVersion)
        .where(
            AssetVersion.asset_id == asset.id,
            AssetVersion.source_hash == asset.current_source_hash,
            AssetVersion.content_origin == "source_metadata",
        )
        .limit(1)
    )


async def save_draft(session, asset_id, content: ContentDraft, *, expected_source_hash=None):
    asset = await session.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise ValueError("资产不存在")
    source = await current_source(session, asset)
    if source is None:
        raise ValueError("缺少真实来源版本")
    if expected_source_hash is not None and source.source_hash != expected_source_hash:
        raise ValueError("来源已变化，请重新核对后起草")
    digest = content_hash(content.model_dump())
    existing = await session.scalar(
        select(AssetVersion).where(
            AssetVersion.asset_id == asset.id,
            AssetVersion.source_hash == source.source_hash,
            AssetVersion.content_hash == digest,
        )
    )
    if existing:
        return existing
    fields = content.model_dump(exclude={"origin"})
    version = AssetVersion(
        asset_id=asset.id,
        source_hash=source.source_hash,
        content_hash=digest,
        source_url=source.source_url,
        repository_document_id=source.repository_document_id,
        content_origin=content.origin,
        **fields,
    )
    session.add(version)
    await session.flush()
    for category in content.categories:
        await session.execute(
            insert(AssetCategoryLink)
            .values(asset_id=asset.id, category_id=category, evidence="维护草稿分类；发布仍需审核")
            .on_conflict_do_nothing()
        )
    return version


def review_metadata(*, reviewer, confirmed, review_actor, authorization_ref):
    if not confirmed or not 1 <= len(reviewer.strip()) <= 120:
        raise ValueError("必须提供明确的人工审核确认及审核人")
    is_ai = reviewer.strip().casefold().startswith("ai:")
    if review_actor == "human":
        if is_ai:
            raise ValueError("AI 审核人必须使用明确的委托 AI 审核路径")
        return {"actor_type": "human"}
    if review_actor != "delegated_ai":
        raise ValueError("未知审核类型")
    if not is_ai or not authorization_ref or not 1 <= len(authorization_ref.strip()) <= 500:
        raise ValueError("委托 AI 审核需要 ai: 审核人和明确的用户授权依据")
    return {"actor_type": "delegated_ai", "authorization_ref": authorization_ref.strip()}


async def publish_version(
    session,
    version_id,
    *,
    reviewer,
    confirmed,
    note="",
    review_actor="human",
    authorization_ref=None,
):
    metadata = review_metadata(
        reviewer=reviewer,
        confirmed=confirmed,
        review_actor=review_actor,
        authorization_ref=authorization_ref,
    )
    version = await session.get(AssetVersion, version_id)
    if version is None:
        raise ValueError("内容版本不存在")
    asset = await session.scalar(
        select(Asset).where(Asset.id == version.asset_id).with_for_update()
    )
    source = await current_source(session, asset)
    if not version.summary_zh or not re.search(r"[一-鿿]", version.summary_zh):
        raise ValueError("中文内容未就绪")
    if not source or source.source_hash != version.source_hash or not source.source_url:
        raise ValueError("来源已变化或缺少可追溯依据，请重新起草审核")
    if not version.categories:
        raise ValueError("待发布版本缺少已审分类")
    repos = (
        await session.scalars(
            select(Repository).join(AssetRepository).where(AssetRepository.asset_id == asset.id)
        )
    ).all()
    for repo in repos:
        if (
            repo.availability != "active"
            or repo.archived
            or not repo.pushed_at
            or datetime.now(UTC) - repo.pushed_at > timedelta(days=180)
        ):
            raise ValueError("来源可用性或近期更新条件未满足")
    if asset.source_id == "github" and not source.repository_document_id:
        raise ValueError("GitHub 条目缺少 README 来源文档")
    if not await session.scalar(
        select(AssetCategoryLink.asset_id).where(AssetCategoryLink.asset_id == asset.id).limit(1)
    ):
        raise ValueError("缺少场景分类")
    if asset.review_state == "withdrawn":
        raise ValueError("已撤下条目需要先核实来源，不能直接重新发布")
    if version.status != "approved":
        version.status, version.reviewed_by, version.reviewed_at = (
            "approved",
            reviewer.strip(),
            datetime.now(UTC),
        )
        version.review_note = note
        version.raw_data = {
            **version.raw_data,
            "review": {**metadata, "decision": "approved"},
        }
    asset.published_version_id, asset.review_state = version.id, "approved"


async def defer_asset(
    session,
    asset_id,
    *,
    expected_source_hash,
    reviewer,
    confirmed,
    note,
    review_actor="human",
    authorization_ref=None,
):
    metadata = review_metadata(
        reviewer=reviewer,
        confirmed=confirmed,
        review_actor=review_actor,
        authorization_ref=authorization_ref,
    )
    if not note.strip():
        raise ValueError("暂缓收录必须记录具体依据")
    asset = await session.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise ValueError("资产不存在")
    if asset.published_version_id:
        raise ValueError("已发布条目应使用撤下流程，暂缓不能覆盖发布指针")
    source = await current_source(session, asset)
    if source is None or source.source_hash != expected_source_hash:
        raise ValueError("来源已变化或缺失，请重新核对")
    digest = content_hash(
        {"action": "deferred", "source_hash": source.source_hash, "note": note, **metadata}
    )
    existing = await session.scalar(
        select(AssetVersion).where(
            AssetVersion.asset_id == asset.id, AssetVersion.content_hash == digest
        )
    )
    if existing:
        return existing
    decision = AssetVersion(
        asset_id=asset.id,
        source_hash=source.source_hash,
        content_hash=digest,
        source_url=source.source_url,
        repository_document_id=source.repository_document_id,
        content_origin="assistant_draft" if review_actor == "delegated_ai" else "human",
        status="rejected",
        reviewed_by=reviewer.strip(),
        reviewed_at=datetime.now(UTC),
        review_note=note,
        raw_data={"review": {**metadata, "decision": "deferred"}},
    )
    session.add(decision)
    await session.flush()
    return decision


async def withdraw_asset(session, asset_id, *, reviewer, confirmed, note):
    if not confirmed or not reviewer.strip() or not note.strip():
        raise ValueError("撤下需要维护人、确认与依据")
    asset = await session.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise ValueError("资产不存在")
    source = await current_source(session, asset)
    if source is None:
        raise ValueError("缺少真实来源版本，请先核实来源")
    digest = content_hash({"action": "withdraw", "reviewer": reviewer, "note": note})
    if not await session.scalar(
        select(AssetVersion.id).where(
            AssetVersion.asset_id == asset.id, AssetVersion.content_hash == digest
        )
    ):
        session.add(
            AssetVersion(
                asset_id=asset.id,
                source_hash=source.source_hash,
                content_hash=digest,
                content_origin="human",
                status="rejected",
                reviewed_by=reviewer,
                reviewed_at=datetime.now(UTC),
                review_note=note,
            )
        )
    asset.review_state = "withdrawn"
