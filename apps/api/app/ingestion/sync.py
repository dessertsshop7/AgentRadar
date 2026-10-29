"""有界采集任务；数据库事务级 advisory lock 覆盖整个来源任务。"""

import asyncio
import hashlib
import logging
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import (
    Asset,
    AssetCategory,
    AssetCategoryLink,
    AssetRepository,
    AssetVersion,
    Repository,
    RepositoryDocument,
    RepositorySnapshot,
    Source,
    SyncError,
    SyncJob,
    TrendScore,
)
from app.ingestion.providers import GitHubRepositoryAdapter, MCPRegistryAdapter, ProviderError
from app.ingestion.rules import CATEGORIES, calculate_trend, classify, content_hash

logger = logging.getLogger("agentradar")
BASES = {"github": "https://api.github.com", "mcp": "https://registry.modelcontextprotocol.io"}


class GitHubRecord(BaseModel):
    id: int = Field(gt=0)
    full_name: str = Field(max_length=300, pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    html_url: str
    description: str | None = Field(default=None, max_length=20000)
    stargazers_count: int = Field(default=0, ge=0)
    forks_count: int = Field(default=0, ge=0)
    pushed_at: datetime | None = None
    created_at: datetime | None = None
    license: dict | None = None
    topics: list[str] = Field(default_factory=list, max_length=100)
    archived: bool = False
    disabled: bool = False
    private: bool = False

    @field_validator("html_url")
    @classmethod
    def safe_url(cls, value):
        url = urlsplit(value)
        if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password:
            raise ValueError("仅接受公开 GitHub 来源")
        return value


class RegistryServer(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=20000)
    version: str = Field(min_length=1, max_length=120)


def default_queries(now):
    cutoff = (now - timedelta(days=180)).date().isoformat()
    return [
        f"topic:{topic} stars:{stars} archived:false pushed:>={cutoff}"
        for topic in ("rag", "ai-agent", "mcp", "llm-framework")
        for stars in ("20..99", "100..499", "500..1999", ">=2000")
    ]


class SyncService:
    def __init__(self, engine, settings, *, github=None, mcp=None, clock=None):
        self.engine = engine
        self.settings = settings
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.github = github
        self.mcp = mcp
        self.clock = clock or (lambda: datetime.now(UTC))

    async def reference_data(self):
        async with self.sessions.begin() as session:
            for key, label in (("github", "GitHub"), ("mcp", "官方 MCP Registry")):
                await session.execute(
                    insert(Source)
                    .values(id=key, label=label, base_url=BASES[key], enabled=True)
                    .on_conflict_do_nothing()
                )
            for key, (label, _) in CATEGORIES.items():
                await session.execute(
                    insert(AssetCategory).values(id=key, label=label).on_conflict_do_nothing()
                )

    async def run(
        self,
        source_id,
        *,
        queries=None,
        max_records=None,
        readme_limit=None,
        due_only=False,
        trigger="manual",
    ):
        if source_id not in BASES:
            raise ValueError("未知来源")
        max_records = (
            (
                self.settings.sync_max_records
                if source_id == "github"
                else self.settings.sync_mcp_limit
            )
            if max_records is None
            else max_records
        )
        readme_limit = self.settings.sync_readme_limit if readme_limit is None else readme_limit
        if not 1 <= max_records <= 10000 or not 0 <= readme_limit <= 200:
            raise ValueError("采集规模超出边界")
        await self.reference_data()
        lock_key = int.from_bytes(
            hashlib.sha256(("agentradar:" + source_id).encode()).digest()[:8], "big", signed=True
        )
        async with self.engine.connect() as lock_connection, lock_connection.begin():
            # 独立连接只持有事务级锁；数据事务短提交。断进程会由 PostgreSQL 自动释放锁。
            locked = await lock_connection.scalar(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_key}
            )
            if not locked:
                return {"status": "locked"}
            now = self.clock()
            async with self.sessions.begin() as session:
                source = await session.get(Source, source_id)
                orphans = (
                    await session.scalars(
                        select(SyncJob).where(
                            SyncJob.source_id == source_id, SyncJob.status == "running"
                        )
                    )
                ).all()
                for orphan in orphans:
                    orphan.status, orphan.finished_at = "interrupted", now
                    session.add(
                        SyncError(
                            job_id=orphan.id,
                            code="PROCESS_INTERRUPTED",
                            message="重新取得来源锁，恢复未完成任务；后续任务幂等重采。",
                        )
                    )
                if due_only and (
                    not source.enabled
                    or (
                        source.last_success_at
                        and now - source.last_success_at
                        < timedelta(hours=self.settings.sync_interval_hours)
                    )
                    or (source.retry_after and now < source.retry_after)
                ):
                    return {"status": "not_due"}
                job = SyncJob(
                    source_id=source_id, trigger=trigger, started_at=now, status="running"
                )
                session.add(job)
                await session.flush()
                job_id = job.id
            counts = {
                "discovered": 0,
                "repositories": 0,
                "assets": 0,
                "readmes_fetched": 0,
                "readmes_unchanged": 0,
                "readmes_missing": 0,
                "errors": 0,
            }
            coverage = {"queries": [], "incomplete": False, "scan_started_at": now.isoformat()}
            try:
                async with AsyncExitStack() as stack:
                    if source_id == "github":
                        adapter = self.github
                        if adapter is None:
                            if (
                                not self.settings.github_token
                                or not self.settings.github_token.get_secret_value().strip()
                            ):
                                raise ProviderError("GITHUB_TOKEN_MISSING")
                            client = await stack.enter_async_context(
                                httpx.AsyncClient(
                                    base_url=BASES[source_id],
                                    timeout=15,
                                    headers={
                                        "Authorization": "Bearer "
                                        + self.settings.github_token.get_secret_value(),
                                        "Accept": "application/vnd.github+json",
                                        "X-GitHub-Api-Version": "2026-03-10",
                                        "User-Agent": "AgentRadar-P02",
                                    },
                                )
                            )
                            adapter = GitHubRepositoryAdapter(client)
                        await self._github(
                            adapter,
                            job_id,
                            counts,
                            coverage,
                            queries if queries is not None else default_queries(now),
                            max_records,
                            readme_limit,
                        )
                    else:
                        adapter = self.mcp
                        if adapter is None:
                            client = await stack.enter_async_context(
                                httpx.AsyncClient(
                                    base_url=BASES[source_id],
                                    timeout=15,
                                    headers={"User-Agent": "AgentRadar-P02"},
                                )
                            )
                            adapter = MCPRegistryAdapter(client)
                        await self._mcp(adapter, job_id, counts, coverage, max_records)
            except ProviderError as exc:
                await self._error(job_id, counts, exc.code)
                if exc.retry_after:
                    coverage["retry_after_seconds"] = exc.retry_after
                coverage["incomplete"] = True
            except asyncio.CancelledError:
                await self._finish(job_id, source_id, "interrupted", counts, coverage)
                raise
            except Exception as exc:
                logger.error(
                    "sync_internal_error",
                    extra={"job_id": str(job_id), "error_type": type(exc).__name__},
                )
                await self._error(job_id, counts, "INTERNAL_ERROR")
                await self._finish(job_id, source_id, "failed", counts, coverage)
                raise
            status = (
                "succeeded"
                if not counts["errors"] and not coverage["incomplete"]
                else ("partial" if counts["discovered"] else "failed")
            )
            await self._finish(job_id, source_id, status, counts, coverage)
            return {"job_id": str(job_id), "status": status, "counts": counts, "coverage": coverage}

    async def _error(self, job_id, counts, code, item_key=None, *, warning=False):
        if not warning:
            counts["errors"] += 1
        async with self.sessions.begin() as session:
            session.add(
                SyncError(
                    job_id=job_id,
                    code=code,
                    item_key=str(item_key)[:300] if item_key is not None else None,
                    message="来源处理需要检查：" + code,
                )
            )

    async def _finish(self, job_id, source_id, status, counts, coverage):
        now = self.clock()
        async with self.sessions.begin() as session:
            job, source = await session.get(SyncJob, job_id), await session.get(Source, source_id)
            job.status, job.finished_at, job.counts, job.coverage = status, now, counts, coverage
            if status == "succeeded":
                source.last_success_at, source.retry_after = now, None
            else:
                # 定额截断不立即重复轰炸同一查询；失败任务短退避，均不推进成功水位。
                delay = (
                    self.settings.sync_interval_hours * 3600
                    if coverage.get("incomplete") and not counts["errors"]
                    else max(600, coverage.get("retry_after_seconds", 0))
                )
                source.retry_after = now + timedelta(seconds=delay)
        logger.info(
            "sync_finished",
            extra={
                "job_id": str(job_id),
                "source_id": source_id,
                "sync_status": status,
                "counts": counts,
            },
        )

    async def _github(self, adapter, job_id, counts, coverage, queries, limit, readme_limit):
        seen, readmes_used = set(), 0
        for query in queries:
            if len(seen) >= limit:
                coverage["incomplete"] = True
                break
            result = await adapter.discover(query, limit=min(1000, limit - len(seen)))
            coverage["queries"].append(
                {
                    "query": query,
                    "total_reported": result.total,
                    "returned": len(result.records),
                    "pages": result.pages,
                    "incomplete": result.incomplete,
                }
            )
            coverage["incomplete"] |= result.incomplete
            for raw in result.records:
                external_id = str(raw.get("id", ""))
                if external_id in seen:
                    continue
                seen.add(external_id)
                counts["discovered"] += 1
                try:
                    item = GitHubRecord.model_validate(raw)
                    if item.private:
                        raise ProviderError("NON_PUBLIC_REPOSITORY")
                    async with self.sessions() as session:
                        previous = await session.scalar(
                            select(Repository).where(
                                Repository.source_id == "github",
                                Repository.external_id == external_id,
                            )
                        )
                        needs_readme = (
                            previous is None
                            or previous.readme_hash is None
                            or previous.readme_checked_pushed_at != item.pushed_at
                        )
                        etag = previous.readme_etag if previous else None
                    readme = None
                    if needs_readme and readmes_used < readme_limit:
                        readmes_used += 1
                        detail = await adapter.repository(item.full_name)
                        item = GitHubRecord.model_validate(detail)
                        if str(item.id) != external_id or item.private:
                            raise ProviderError("REPOSITORY_ID_MISMATCH")
                        raw = detail
                        readme = await adapter.readme(item.full_name, etag)
                    await self._store_github(item, raw, readme, job_id, counts)
                    if readme and readme.status == "missing":
                        await self._error(
                            job_id, counts, "README_MISSING", external_id, warning=True
                        )
                except ValidationError:
                    await self._error(job_id, counts, "SCHEMA_CHANGED", external_id)
                except ProviderError as exc:
                    await self._error(job_id, counts, exc.code, external_id)
                    if exc.code in {
                        "NOT_FOUND_OR_INACCESSIBLE",
                        "NON_PUBLIC_REPOSITORY",
                        "REPOSITORY_ID_MISMATCH",
                    }:
                        async with self.sessions.begin() as session:
                            await session.execute(
                                update(Repository)
                                .where(
                                    Repository.source_id == "github",
                                    Repository.external_id == external_id,
                                )
                                .values(availability="unverified")
                            )
                    if exc.code in {"RATE_LIMITED", "AUTHENTICATION_FAILED", "FORBIDDEN"}:
                        if exc.retry_after:
                            coverage["retry_after_seconds"] = exc.retry_after
                        coverage["incomplete"] = True
                        return
                if len(seen) % 100 == 0:
                    logger.info("sync_progress", extra={"job_id": str(job_id), "counts": counts})

    async def _store_github(self, item, raw, readme, job_id, counts):
        now = self.clock()
        async with self.sessions.begin() as session:
            repo = await session.scalar(
                select(Repository).where(
                    Repository.source_id == "github", Repository.external_id == str(item.id)
                )
            )
            if repo is None:
                repo = Repository(source_id="github", external_id=str(item.id))
                session.add(repo)
            for key, value in {
                "full_name": item.full_name,
                "canonical_url": item.html_url,
                "description": item.description,
                "license": (item.license or {}).get("spdx_id"),
                "stars": item.stargazers_count,
                "forks": item.forks_count,
                "archived": item.archived,
                "pushed_at": item.pushed_at,
                "source_created_at": item.created_at,
                "collected_at": now,
                "raw_data": raw,
                "availability": "withdrawn" if item.archived or item.disabled else "active",
            }.items():
                setattr(repo, key, value)
            if repo.license == "NOASSERTION":
                repo.license = None
            await session.flush()
            document = None
            if readme:
                if readme.status == "content":
                    digest = content_hash(readme.body)
                    if digest != repo.readme_hash:
                        counts["readmes_fetched"] += 1
                    else:
                        counts["readmes_unchanged"] += 1
                    document = await session.scalar(
                        select(RepositoryDocument).where(
                            RepositoryDocument.repository_id == repo.id,
                            RepositoryDocument.content_hash == digest,
                        )
                    )
                    if document is None:
                        document = RepositoryDocument(
                            repository_id=repo.id,
                            content_hash=digest,
                            body=readme.body,
                            source_url=BASES["github"] + "/repos/" + item.full_name + "/readme",
                            etag=readme.etag,
                            fetched_at=now,
                        )
                        session.add(document)
                        await session.flush()
                    repo.readme_hash, repo.readme_etag = digest, readme.etag
                    repo.readme_checked_pushed_at = item.pushed_at
                elif readme.status == "unchanged":
                    counts["readmes_unchanged"] += 1
                    repo.readme_checked_pushed_at = item.pushed_at
                else:
                    counts["readmes_missing"] += 1
                    if repo.readme_hash:
                        repo.availability = "unverified"
            if document is None and repo.readme_hash:
                document = await session.scalar(
                    select(RepositoryDocument).where(
                        RepositoryDocument.repository_id == repo.id,
                        RepositoryDocument.content_hash == repo.readme_hash,
                    )
                )
            asset = await session.scalar(
                select(Asset)
                .where(Asset.source_id == "github", Asset.external_id == str(item.id))
                .with_for_update()
            )
            if asset is None:
                kinds = classify((item.description or "") + " " + item.full_name, item.topics)
                kind = (
                    "mcp"
                    if "mcp-integration" in kinds
                    else "framework"
                    if "framework" in kinds
                    else "agent"
                    if "agent-workflow" in kinds
                    else "tool"
                )
                asset = Asset(
                    source_id="github",
                    external_id=str(item.id),
                    slug="gh-" + str(item.id),
                    name=item.full_name,
                    asset_type=kind,
                )
                session.add(asset)
                await session.flush()
                session.add(
                    AssetRepository(asset_id=asset.id, repository_id=repo.id, is_primary=True)
                )
            asset.name, asset.collected_at = item.full_name, now
            stable = {
                "id": item.id,
                "description": item.description,
                "license": repo.license,
                "topics": item.topics,
            }
            digest = document.content_hash if document else content_hash(stable)
            await self._source_version(
                session,
                asset,
                digest,
                raw,
                document.source_url if document else item.html_url,
                document,
            )
            await self._categories(
                session,
                asset.id,
                classify((item.description or "") + " " + item.full_name, item.topics),
            )
            await session.execute(
                insert(RepositorySnapshot)
                .values(
                    repository_id=repo.id,
                    job_id=job_id,
                    observed_at=now,
                    stars=repo.stars,
                    forks=repo.forks,
                )
                .on_conflict_do_nothing(index_elements=["repository_id", "job_id"])
            )
            await session.flush()
            await self._trend(session, asset, repo)
        counts["repositories"] += 1
        counts["assets"] += 1

    async def _source_version(self, session, asset, digest, raw, source_url, document=None):
        asset.current_source_hash = digest
        version = await session.scalar(
            select(AssetVersion).where(
                AssetVersion.asset_id == asset.id,
                AssetVersion.source_hash == digest,
                AssetVersion.content_origin == "source_metadata",
            )
        )
        if version is None:
            version = AssetVersion(
                asset_id=asset.id,
                source_hash=digest,
                content_hash=content_hash({"source": digest}),
                raw_data=raw,
                source_url=source_url,
                repository_document_id=document.id if document else None,
                created_at=self.clock(),
            )
            session.add(version)
        if asset.published_version_id and asset.review_state != "withdrawn":
            published = await session.get(AssetVersion, asset.published_version_id)
            asset.review_state = "approved" if published.source_hash == digest else "needs_review"
        return version

    async def _categories(self, session, asset_id, categories):
        for category, evidence in categories.items():
            await session.execute(
                insert(AssetCategoryLink)
                .values(asset_id=asset_id, category_id=category, evidence=evidence)
                .on_conflict_do_nothing()
            )

    async def _trend(self, session, asset, repo):
        observations = (
            await session.execute(
                select(RepositorySnapshot.observed_at, RepositorySnapshot.stars)
                .where(RepositorySnapshot.repository_id == repo.id)
                .order_by(RepositorySnapshot.observed_at)
            )
        ).all()
        values = calculate_trend(
            observations, repo.pushed_at, repo.source_created_at, bool(repo.readme_hash)
        )
        await session.execute(
            insert(TrendScore)
            .values(asset_id=asset.id, **values)
            .on_conflict_do_update(index_elements=["asset_id"], set_=values)
        )

    async def _mcp(self, adapter, job_id, counts, coverage, limit):
        async with self.sessions() as session:
            previous = await session.scalar(
                select(SyncJob)
                .where(SyncJob.source_id == "mcp", SyncJob.id != job_id)
                .order_by(SyncJob.started_at.desc())
                .limit(1)
            )
            previous_coverage = previous.coverage if previous else {}
        continuing = previous_coverage.get("cycle_in_progress", False)
        cursor = previous_coverage.get("resume_cursor") if continuing else None
        since = (
            previous_coverage.get("updated_since")
            if continuing
            else previous_coverage.get("scan_started_at")
            if previous and previous.status == "succeeded"
            else None
        )
        if continuing:
            coverage["scan_started_at"] = previous_coverage["scan_started_at"]
        coverage.update(updated_since=since, resume_cursor=cursor, cycle_in_progress=True)
        result = await adapter.discover(limit=limit, cursor=cursor, updated_since=since)
        coverage["incomplete"] = result.incomplete
        coverage["pages"] = result.pages
        for raw in result.records:
            counts["discovered"] += 1
            try:
                server = RegistryServer.model_validate(raw.get("server", {}))
                async with self.sessions.begin() as session:
                    asset = await session.scalar(
                        select(Asset)
                        .where(Asset.source_id == "mcp", Asset.external_id == server.name)
                        .with_for_update()
                    )
                    if asset is None:
                        asset = Asset(
                            source_id="mcp",
                            external_id=server.name,
                            slug="mcp-" + content_hash(server.name)[:24],
                            name=server.name,
                            asset_type="mcp",
                        )
                        session.add(asset)
                        await session.flush()
                    asset.collected_at = self.clock()
                    official = raw.get("_meta", {}).get(
                        "io.modelcontextprotocol.registry/official", {}
                    )
                    if official.get("status") == "deleted":
                        asset.review_state = "withdrawn"
                    source_url = (
                        BASES["mcp"]
                        + "/v0.1/servers/"
                        + quote(server.name, safe="")
                        + "/versions/"
                        + quote(server.version, safe="")
                    )
                    await self._source_version(
                        session, asset, content_hash(raw["server"]), raw, source_url
                    )
                    await self._categories(
                        session,
                        asset.id,
                        {
                            **classify(server.description, []),
                            "mcp-integration": "registry-v0.1:server",
                        },
                    )
                    repository_url = raw["server"].get("repository", {}).get("url", "")
                    parsed = urlsplit(repository_url)
                    if parsed.scheme == "https" and parsed.hostname == "github.com":
                        full_name = parsed.path.strip("/").removesuffix(".git")
                        repo = await session.scalar(
                            select(Repository).where(
                                Repository.source_id == "github", Repository.full_name == full_name
                            )
                        )
                        if repo:
                            primary = await session.scalar(
                                select(AssetRepository.repository_id).where(
                                    AssetRepository.asset_id == asset.id, AssetRepository.is_primary
                                )
                            )
                            await session.execute(
                                insert(AssetRepository)
                                .values(
                                    asset_id=asset.id,
                                    repository_id=repo.id,
                                    is_primary=primary is None,
                                )
                                .on_conflict_do_nothing()
                            )
                            if primary is None or primary == repo.id:
                                await self._trend(session, asset, repo)
                counts["assets"] += 1
            except (ValidationError, AttributeError, TypeError):
                await self._error(job_id, counts, "SCHEMA_CHANGED")
                coverage["resume_cursor"] = cursor  # 记录失败时重放当前批次，不跳过失败记录。
        if counts["errors"] == 0:
            coverage["resume_cursor"] = result.next_cursor
            coverage["cycle_in_progress"] = result.incomplete

    async def tick(self):
        for source_id in BASES:
            await self.run(source_id, due_only=True, trigger="scheduler")
