"""只读取已审版本；查询不触发采集或模型调用。"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import String, and_, cast, exists, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Asset,
    AssetCategory,
    AssetRepository,
    AssetVersion,
    Repository,
    TrendScore,
)
from app.db.session import get_session

router = APIRouter()
logger = logging.getLogger("agentradar")
Category = Literal["knowledge", "agent-workflow", "mcp-integration", "framework"]
Difficulty = Literal["unknown", "beginner", "visual", "developer"]


class AssetItem(BaseModel):
    id: UUID
    slug: str
    name: str
    kind: str
    summary_zh: str
    description_zh: str | None
    difficulty: str
    cost: str
    tags: list[str]
    scenarios: list[str]
    requirements: list[str]
    limitations: list[str]
    categories: list[str]
    content_version_id: UUID
    source_hash: str
    origin: str
    review: dict
    needs_review: bool
    collected_at: datetime
    sources: list[dict]
    trend: dict | None = None


class AssetList(BaseModel):
    items: list[AssetItem]
    total: int
    page: int
    page_size: int
    request_id: str


class AssetDetail(BaseModel):
    item: AssetItem
    request_id: str


async def public_session(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AsyncIterator[AsyncSession]:
    try:
        async with asyncio.timeout(request.app.state.settings.database_timeout_seconds):
            yield session
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.warning(
            "catalog_unavailable",
            extra={"request_id": request.state.request_id, "error_type": type(exc).__name__},
        )
        raise HTTPException(503) from None


Database = Annotated[AsyncSession, Depends(public_session)]


def public_query():
    unavailable_repository = exists(
        select(AssetRepository.asset_id)
        .join(Repository)
        .where(AssetRepository.asset_id == Asset.id, Repository.availability != "active")
    )
    return (
        select(Asset, AssetVersion)
        .join(
            AssetVersion,
            and_(Asset.published_version_id == AssetVersion.id, AssetVersion.asset_id == Asset.id),
        )
        .where(
            Asset.review_state.in_(["approved", "needs_review"]),
            AssetVersion.status == "approved",
            AssetVersion.summary_zh.is_not(None),
            AssetVersion.reviewed_by.is_not(None),
            AssetVersion.reviewed_at.is_not(None),
            func.jsonb_array_length(AssetVersion.categories) > 0,
            ~unavailable_repository,
        )
    )


async def serialize(session: AsyncSession, rows, trends=False):
    ids = [asset.id for asset, _ in rows]
    sources: dict = {key: [] for key in ids}
    if ids:
        for link, repo in (
            await session.execute(
                select(AssetRepository, Repository)
                .join(Repository)
                .where(AssetRepository.asset_id.in_(ids))
                .order_by(Repository.id)
            )
        ).all():
            sources[link.asset_id].append(
                {
                    "provider": "github",
                    "external_id": repo.external_id,
                    "url": repo.canonical_url,
                    "license": repo.license or "unknown",
                    "collected_at": repo.collected_at.isoformat(),
                    "primary": link.is_primary,
                }
            )
    scores = {}
    if trends and ids:
        scores = {
            score.asset_id: score
            for score in (
                await session.scalars(select(TrendScore).where(TrendScore.asset_id.in_(ids)))
            ).all()
        }
    items = []
    for asset, version in rows:
        item = {
            "id": asset.id,
            "slug": asset.slug,
            "name": version.name_zh or asset.name,
            "kind": asset.asset_type,
            "summary_zh": version.summary_zh,
            "description_zh": version.description_zh,
            "difficulty": version.difficulty,
            "cost": version.cost,
            "tags": version.tags,
            "scenarios": version.scenarios,
            "requirements": version.requirements,
            "limitations": version.limitations,
            "categories": version.categories,
            "content_version_id": version.id,
            "source_hash": version.source_hash,
            "origin": version.content_origin,
            "review": {
                "actor_type": version.raw_data.get("review", {}).get("actor_type", "unknown"),
                "reviewed_by": version.reviewed_by,
                "reviewed_at": version.reviewed_at.isoformat(),
            },
            "needs_review": asset.review_state == "needs_review",
            "collected_at": asset.collected_at,
            "sources": sources[asset.id],
        }
        if version.source_url:
            item["sources"].append(
                {
                    "provider": asset.source_id,
                    "url": version.source_url,
                    "source_hash": version.source_hash,
                }
            )
        if score := scores.get(asset.id):
            item["trend"] = {
                "score": score.score,
                "formula_version": score.formula_version,
                "components": score.components,
                "star_growth": score.star_growth,
                "sample_count": score.sample_count,
                "window_start": score.window_start.isoformat(),
                "window_end": score.window_end.isoformat(),
                "growth_known": score.star_growth is not None,
            }
        items.append(item)
    return items


@router.get("/assets", response_model=AssetList)
async def assets(
    request: Request,
    response: Response,
    session: Database,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category: Category | None = None,
    difficulty: Difficulty | None = None,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    sort: Literal["slug", "updated"] = "slug",
):
    query = public_query()
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                *[
                    column.ilike(pattern, escape="\\")
                    for column in (
                        Asset.name,
                        AssetVersion.name_zh,
                        AssetVersion.summary_zh,
                        AssetVersion.description_zh,
                        cast(AssetVersion.tags, String),
                        cast(AssetVersion.scenarios, String),
                    )
                ]
            )
        )
    if category:
        query = query.where(AssetVersion.categories.contains([category]))
    if difficulty:
        query = query.where(AssetVersion.difficulty == difficulty)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    ordering = (Asset.slug,) if sort == "slug" else (Asset.collected_at.desc(), Asset.slug)
    rows = (
        await session.execute(
            query.order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    response.headers["Cache-Control"] = "public, max-age=30"
    return {
        "items": await serialize(session, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "request_id": request.state.request_id,
    }


@router.get("/assets/{asset_id}", response_model=AssetDetail)
async def asset_detail(asset_id: str, request: Request, response: Response, session: Database):
    try:
        identity = Asset.id == UUID(asset_id)
    except ValueError:
        identity = Asset.slug == asset_id
    row = (await session.execute(public_query().where(identity))).first()
    if not row:
        raise HTTPException(404)
    response.headers["Cache-Control"] = "public, max-age=30"
    return {"item": (await serialize(session, [row]))[0], "request_id": request.state.request_id}


@router.get("/categories")
async def categories(request: Request, session: Database):
    visible = public_query().with_only_columns(Asset.id, AssetVersion.categories).subquery()
    rows = (
        await session.execute(
            select(
                AssetCategory.id,
                AssetCategory.label,
                func.count(func.distinct(visible.c.id)),
            )
            .join(visible, visible.c.categories.op("?")(AssetCategory.id))
            .group_by(AssetCategory.id)
            .order_by(AssetCategory.id)
        )
    ).all()
    return {
        "items": [{"id": key, "label": label, "count": count} for key, label, count in rows],
        "request_id": request.state.request_id,
    }


@router.get("/trending", response_model=AssetList)
async def trending(
    request: Request,
    session: Database,
    page: Annotated[int, Query(ge=1, le=10000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
):
    query = public_query().join(TrendScore, TrendScore.asset_id == Asset.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.execute(
            query.order_by(TrendScore.score.desc(), Asset.slug)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": await serialize(session, rows, trends=True),
        "total": total,
        "page": page,
        "page_size": page_size,
        "request_id": request.state.request_id,
    }
