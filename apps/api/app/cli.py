"""本机/容器维护入口：需操作系统访问权及数据库凭据，不提供匿名 HTTP 写接口。"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.api.assets import public_query
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.models import (
    Asset,
    AssetCategoryLink,
    Repository,
    RepositorySnapshot,
    SyncError,
    SyncJob,
)
from app.db.session import create_database_engine
from app.ingestion.maintenance import (
    ContentDraft,
    current_source,
    defer_asset,
    publish_version,
    save_draft,
    withdraw_asset,
)
from app.ingestion.rules import read_skill_metadata
from app.ingestion.sync import SyncService


def parser():
    root = argparse.ArgumentParser(description="AgentRadar P02 受控维护；所有外部文档只作为数据")
    commands = root.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync", help="真实采集；默认不自动发布")
    sync.add_argument("--source", required=True, choices=["github", "mcp"])
    sync.add_argument(
        "--query", action="append", help="GitHub 查询，可重复；不传则使用分主题/Stars 的近期计划"
    )
    sync.add_argument("--max-records", type=int)
    sync.add_argument("--readme-limit", type=int)
    sync.add_argument("--if-due", action="store_true")
    commands.add_parser("stats", help="真实库规模、README 覆盖与发布数量")
    jobs = commands.add_parser("jobs", help="查看真实任务及安全错误代码")
    jobs.add_argument("--job-id", type=UUID)
    export = commands.add_parser("export-review", help="导出未审核清单，不覆盖现有文件")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument(
        "--with-readme", action="store_true", help="只导出有真实 README 证据的首批候选"
    )
    draft = commands.add_parser("draft", help="导入中文草稿，绑定明确的来源哈希")
    draft.add_argument("--asset", type=UUID, required=True)
    draft.add_argument("--source-hash", required=True)
    draft.add_argument("--file", type=Path, required=True)
    publish = commands.add_parser("publish", help="受控发布；区分人工与用户委托 AI 审核")
    publish.add_argument("--version", type=UUID, required=True)
    defer = commands.add_parser("defer", help="记录暂缓收录依据，保留原始资料和待审状态")
    defer.add_argument("--asset", type=UUID, required=True)
    defer.add_argument("--source-hash", required=True)
    for review in (publish, defer):
        review.add_argument("--reviewer", required=True)
        confirmation = review.add_mutually_exclusive_group()
        confirmation.add_argument("--confirm-human-review", action="store_true")
        confirmation.add_argument("--confirm-delegated-ai-review", action="store_true")
        review.add_argument("--authorization-ref", help="委托 AI 审核所依据的明确用户授权记录")
        review.add_argument("--note", default="")
    withdraw = commands.add_parser("withdraw", help="有依据地撤下资产并保留历史")
    withdraw.add_argument("--asset", type=UUID, required=True)
    withdraw.add_argument("--reviewer", required=True)
    withdraw.add_argument("--confirm-human-review", action="store_true")
    withdraw.add_argument("--note", required=True)
    skill = commands.add_parser(
        "inspect-skill", help="仅解析显式可信目录元信息，不执行指令或自动发布"
    )
    skill.add_argument("--file", type=Path, required=True)
    skill.add_argument("--trusted-root", type=Path, required=True)
    return root


async def inventory(session):
    def count(model):
        return select(func.count()).select_from(model)

    repositories = await session.scalar(count(Repository))
    readmes = await session.scalar(count(Repository).where(Repository.readme_hash.is_not(None)))
    origins = dict(
        (
            await session.execute(select(Asset.source_id, func.count()).group_by(Asset.source_id))
        ).all()
    )
    classified = dict(
        (
            await session.execute(
                select(AssetCategoryLink.category_id, func.count()).group_by(
                    AssetCategoryLink.category_id
                )
            )
        ).all()
    )
    window = (
        await session.execute(
            select(
                func.min(RepositorySnapshot.observed_at), func.max(RepositorySnapshot.observed_at)
            )
        )
    ).one()
    return {
        "measured_at": datetime.now(UTC),
        "github_repositories": repositories,
        "assets_total": await session.scalar(count(Asset)),
        "assets_by_source": origins,
        "mcp_assets": origins.get("mcp", 0),
        "published_assets": await session.scalar(
            select(func.count()).select_from(public_query().subquery())
        ),
        "repositories_with_readme": readmes,
        "readme_coverage": readmes / repositories if repositories else 0,
        "ingestion_categories_overlapping": classified,
        "observations_start": window[0],
        "observations_end": window[1],
    }


async def execute(args):
    if args.command == "inspect-skill":
        return {
            "origin": "explicit-local-directory",
            "executed": False,
            "metadata": read_skill_metadata(args.file, args.trusted_root),
        }
    settings = Settings()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings)
    service = SyncService(engine, settings)
    try:
        if args.command == "sync":
            return await service.run(
                args.source,
                queries=args.query,
                max_records=args.max_records,
                readme_limit=args.readme_limit,
                due_only=args.if_due,
            )
        async with service.sessions.begin() as session:
            if args.command == "stats":
                return await inventory(session)
            if args.command == "jobs":
                query = select(SyncJob).order_by(SyncJob.started_at.desc()).limit(20)
                if args.job_id:
                    query = query.where(SyncJob.id == args.job_id)
                jobs = (await session.scalars(query)).all()
                result = []
                for job in jobs:
                    errors = (
                        await session.scalars(
                            select(SyncError)
                            .where(SyncError.job_id == job.id)
                            .order_by(SyncError.id)
                            .limit(100)
                        )
                    ).all()
                    result.append(
                        {
                            "id": job.id,
                            "source": job.source_id,
                            "status": job.status,
                            "started_at": job.started_at,
                            "finished_at": job.finished_at,
                            "counts": job.counts,
                            "coverage": job.coverage,
                            "errors": [
                                {"code": error.code, "item_key": error.item_key} for error in errors
                            ],
                        }
                    )
                return {"jobs": result}
            if args.command == "export-review":
                items = []
                assets = (
                    await session.scalars(
                        select(Asset)
                        .where(Asset.review_state.in_(["pending", "needs_review"]))
                        .order_by(Asset.slug)
                    )
                ).all()
                for asset in assets:
                    source = await current_source(session, asset)
                    if args.with_readme and not (source and source.repository_document_id):
                        continue
                    categories = list(
                        (
                            await session.scalars(
                                select(AssetCategoryLink.category_id)
                                .where(AssetCategoryLink.asset_id == asset.id)
                                .order_by(AssetCategoryLink.category_id)
                            )
                        ).all()
                    )
                    items.append(
                        {
                            "asset_id": asset.id,
                            "slug": asset.slug,
                            "name": asset.name,
                            "kind": asset.asset_type,
                            "review_state": asset.review_state,
                            "source_hash": source.source_hash if source else None,
                            "source_url": source.source_url if source else None,
                            "has_readme": bool(source and source.repository_document_id),
                            "source_description": source.raw_data.get(
                                "description", source.raw_data.get("server", {}).get("description")
                            )
                            if source
                            else None,
                            "unreviewed_rule_categories": categories,
                            "content_template": {
                                "summary_zh": "",
                                "difficulty": "unknown",
                                "cost": "unknown",
                                "categories": categories,
                                "origin": "assistant_draft",
                                "limitations": ["未进行安装或安全验证"],
                            },
                        }
                    )
                data = {
                    "generated_at": datetime.now(UTC),
                    "status": "pending-human-review",
                    "counts": await inventory(session),
                    "items": items,
                }
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as stream:
                    json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
                return {
                    "output": str(args.output),
                    "pending_items": len(items),
                    "published_by_this_command": 0,
                }
            if args.command == "draft":
                if args.file.stat().st_size > 1_000_000:
                    raise ValueError("草稿文件超过 1 MB")
                data = ContentDraft.model_validate_json(args.file.read_text(encoding="utf-8-sig"))
                version = await save_draft(
                    session, args.asset, data, expected_source_hash=args.source_hash
                )
                return {"version_id": version.id, "status": version.status, "published": False}
            if args.command == "publish":
                await publish_version(
                    session,
                    args.version,
                    reviewer=args.reviewer,
                    confirmed=args.confirm_human_review or args.confirm_delegated_ai_review,
                    note=args.note,
                    review_actor="delegated_ai" if args.confirm_delegated_ai_review else "human",
                    authorization_ref=args.authorization_ref,
                )
                return {"version_id": args.version, "status": "approved"}
            if args.command == "defer":
                decision = await defer_asset(
                    session,
                    args.asset,
                    expected_source_hash=args.source_hash,
                    reviewer=args.reviewer,
                    confirmed=args.confirm_human_review or args.confirm_delegated_ai_review,
                    note=args.note,
                    review_actor="delegated_ai" if args.confirm_delegated_ai_review else "human",
                    authorization_ref=args.authorization_ref,
                )
                return {"asset_id": args.asset, "version_id": decision.id, "status": "deferred"}
            if args.command == "withdraw":
                await withdraw_asset(
                    session,
                    args.asset,
                    reviewer=args.reviewer,
                    confirmed=args.confirm_human_review,
                    note=args.note,
                )
                return {"asset_id": args.asset, "status": "withdrawn"}
    finally:
        await engine.dispose()


def main():
    args = parser().parse_args()
    try:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            result = runner.run(execute(args))
    except ValidationError:
        print(
            json.dumps(
                {"error": "VALIDATION_ERROR", "message": "配置或草稿字段校验失败；未显示输入值。"},
                ensure_ascii=False,
            )
        )
        return 1
    except (OSError, SQLAlchemyError) as exc:
        print(json.dumps({"error": "MAINTENANCE_FAILED", "error_type": type(exc).__name__}))
        return 1
    except ValueError as exc:
        print(json.dumps({"error": "INVALID_OPERATION", "message": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"error": "INTERNAL_ERROR", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 2 if result.get("status") in {"partial", "failed", "interrupted"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
