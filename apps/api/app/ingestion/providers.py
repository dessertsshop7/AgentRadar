import asyncio
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx


class ProviderError(Exception):
    """可持久化的安全错误；不包含响应体、凭据或异常原文。"""

    def __init__(self, code: str, retry_after: float | None = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)


class ProviderHTTP:
    def __init__(self, client: httpx.AsyncClient, *, max_bytes=3_000_000, sleep=asyncio.sleep):
        self.client = client
        self.max_bytes = max_bytes
        self.sleep = sleep
        self.blocked_until: dict[str, float] = {}

    def trusted(self, url: str) -> httpx.URL:
        target = self.client.base_url.join(url)
        base = self.client.base_url
        if (target.scheme, target.host, target.port) != (
            base.scheme,
            base.host,
            base.port,
        ) or target.userinfo:
            raise ProviderError("UNSAFE_REDIRECT")
        return target

    async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
        try:
            async with asyncio.timeout(45):
                return await self._get(url, params=params, headers=headers)
        except TimeoutError:
            raise ProviderError("TIMEOUT") from None

    async def _get(self, url, *, params, headers):
        target = self.trusted(url)
        resource = "search" if target.path.startswith("/search/") else "core"
        until = self.blocked_until.get(resource, 0)
        if until > time.time():
            raise ProviderError("RATE_LIMITED", until - time.time())
        attempts = redirects = 0
        while attempts < 3:
            try:
                async with self.client.stream(
                    "GET", target, params=params, headers=headers, follow_redirects=False
                ) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_bytes:
                            raise ProviderError("RESPONSE_TOO_LARGE")
                    # aiter_bytes 已解压；重建响应不能保留压缩与原长度头。
                    decoded_headers = dict(response.headers)
                    decoded_headers.pop("content-encoding", None)
                    decoded_headers.pop("content-length", None)
                    response = httpx.Response(
                        response.status_code,
                        headers=decoded_headers,
                        content=bytes(content),
                        request=response.request,
                    )
            except httpx.RequestError as exc:
                attempts += 1
                if attempts == 3:
                    raise ProviderError(
                        "TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "NETWORK_ERROR"
                    ) from None
                await self.sleep(0.5 * 2 ** (attempts - 1))
                continue
            if response.status_code in {301, 302, 303, 307, 308}:
                redirects += 1
                if redirects > 3 or not response.headers.get("location"):
                    raise ProviderError("REDIRECT_LIMIT")
                target = self.trusted(str(response.url.join(response.headers["location"])))
                params = None
                continue
            remaining = response.headers.get("x-ratelimit-remaining")
            reset = response.headers.get("x-ratelimit-reset")
            if remaining == "0" and reset:
                try:
                    self.blocked_until[resource] = float(reset)
                except ValueError:
                    pass
            rate_message = ""
            if response.status_code == 403:
                try:
                    payload = response.json()
                    if isinstance(payload, dict) and isinstance(payload.get("message"), str):
                        rate_message = payload["message"].lower()
                except ValueError:
                    pass
            limited = response.status_code == 429 or (
                response.status_code == 403
                and (
                    remaining == "0"
                    or "retry-after" in response.headers
                    or "rate limit" in rate_message
                )
            )
            if limited or response.status_code >= 500:
                attempts += 1
                delay = 60.0 if limited else 0.5 * 2 ** (attempts - 1)
                retry = response.headers.get("retry-after")
                if retry:
                    try:
                        delay = max(0.0, float(retry))
                    except ValueError:
                        try:
                            delay = max(0.0, parsedate_to_datetime(retry).timestamp() - time.time())
                        except (ValueError, TypeError, OverflowError):
                            delay = 60.0
                elif limited and reset:
                    try:
                        delay = max(0.0, float(reset) - time.time())
                    except ValueError:
                        pass
                if attempts == 3 or delay > 30:
                    raise ProviderError(
                        "RATE_LIMITED" if limited else "UPSTREAM_UNAVAILABLE", delay
                    )
                await self.sleep(delay)
                continue
            if response.status_code == 403:
                raise ProviderError("FORBIDDEN")
            if response.status_code == 401:
                raise ProviderError("AUTHENTICATION_FAILED")
            if response.status_code not in {200, 304, 404}:
                raise ProviderError("UPSTREAM_REJECTED")
            return response
        raise ProviderError("RETRY_EXHAUSTED")


def object_json(response):
    try:
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (ValueError, UnicodeError):
        raise ProviderError("SCHEMA_CHANGED") from None


@dataclass
class Discovery:
    records: list[dict] = field(default_factory=list)
    total: int = 0
    pages: int = 0
    incomplete: bool = False
    next_cursor: str | None = None
    next_offset: int | None = None
    search_incomplete: bool = False


@dataclass
class Readme:
    status: str
    body: str | None = None
    etag: str | None = None


class GitHubRepositoryAdapter:
    def __init__(self, client: httpx.AsyncClient):
        self.http = ProviderHTTP(client)

    async def discover(self, query: str, limit=1000, *, offset=None) -> Discovery:
        if offset is not None:
            return await self._window(query, limit, offset)
        result = Discovery()
        url = "/search/repositories"
        params = {"q": query, "per_page": min(100, limit), "sort": "stars", "order": "desc"}
        seen_urls, ids = set(), set()
        while url and result.pages < 10 and len(result.records) < min(limit, 1000):
            if url in seen_urls:
                raise ProviderError("PAGINATION_LOOP")
            seen_urls.add(url)
            response = await self.http.get(url, params=params)
            data = object_json(response)
            if not isinstance(data.get("items"), list) or not isinstance(
                data.get("total_count"), int
            ):
                raise ProviderError("SCHEMA_CHANGED")
            result.total = data["total_count"]
            result.pages += 1
            result.incomplete |= bool(data.get("incomplete_results")) or result.total > 1000
            for item in data["items"]:
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    raise ProviderError("SCHEMA_CHANGED")
                if item["id"] not in ids:
                    ids.add(item["id"])
                    result.records.append(item)
                    if len(result.records) >= min(limit, 1000):
                        break
            url = response.links.get("next", {}).get("url")
            params = None
        result.incomplete |= bool(url)
        return result

    async def _window(self, query, limit, offset):
        """默认计划固定每页 100；预算可在页中耗尽，下一次从记录偏移续读。"""
        if not 0 <= offset < 1000:
            raise ValueError("查询偏移超出 GitHub 搜索窗口")
        result = Discovery()
        position = offset
        while position < 1000 and len(result.records) < limit:
            data = object_json(
                await self.http.get(
                    "/search/repositories",
                    params={
                        "q": query,
                        "per_page": 100,
                        "page": position // 100 + 1,
                        "sort": "stars",
                        "order": "desc",
                    },
                )
            )
            if not isinstance(data.get("items"), list) or not isinstance(
                data.get("total_count"), int
            ):
                raise ProviderError("SCHEMA_CHANGED")
            result.total = data["total_count"]
            result.search_incomplete |= bool(data.get("incomplete_results"))
            result.incomplete |= bool(data.get("incomplete_results")) or result.total > 1000
            result.pages += 1
            items = data["items"][position % 100 :]
            remaining = min(limit - len(result.records), 1000 - position)
            selected = items[:remaining]
            if any(
                not isinstance(item, dict) or not isinstance(item.get("id"), int)
                for item in selected
            ):
                raise ProviderError("SCHEMA_CHANGED")
            result.records.extend(selected)
            position += len(selected)
            if position >= min(result.total, 1000) or not selected:
                break
            if len(result.records) >= limit:
                result.next_offset = position
                result.incomplete = True
                break
            if len(data["items"]) < 100:
                break
        return result

    async def repository(self, full_name: str) -> dict:
        response = await self.http.get("/repos/" + quote(full_name, safe="/"))
        if response.status_code == 404:
            raise ProviderError("NOT_FOUND_OR_INACCESSIBLE")
        return object_json(response)

    async def readme(self, full_name: str, etag: str | None = None) -> Readme:
        headers = {"Accept": "application/vnd.github.raw+json"}
        if etag:
            headers["If-None-Match"] = etag
        response = await self.http.get(
            "/repos/" + quote(full_name, safe="/") + "/readme", headers=headers
        )
        if response.status_code == 304:
            return Readme("unchanged", etag=etag)
        if response.status_code == 404:
            return Readme("missing")
        return Readme("content", body=response.text, etag=response.headers.get("etag"))


class MCPRegistryAdapter:
    def __init__(self, client: httpx.AsyncClient):
        self.http = ProviderHTTP(client)

    async def discover(
        self, limit=100, *, search=None, cursor=None, updated_since=None
    ) -> Discovery:
        try:
            async with asyncio.timeout(60):
                return await self._discover(
                    limit, search=search, cursor=cursor, updated_since=updated_since
                )
        except TimeoutError:
            raise ProviderError("PAGINATION_TIMEOUT") from None

    async def _discover(self, limit, *, search, cursor, updated_since):
        result = Discovery()
        cursors = set()
        while len(result.records) < limit:
            if result.pages >= 100:
                raise ProviderError("PAGINATION_LIMIT")
            params = {"limit": min(100, limit - len(result.records)), "version": "latest"}
            if search:
                params["search"] = search
            if cursor:
                params["cursor"] = cursor
            if updated_since:
                params["updated_since"] = updated_since
            data = object_json(await self.http.get("/v0.1/servers", params=params))
            if not isinstance(data.get("servers"), list) or not isinstance(
                data.get("metadata", {}), dict
            ):
                raise ProviderError("SCHEMA_CHANGED")
            result.records.extend(data["servers"])
            result.pages += 1
            cursor = data.get("metadata", {}).get("nextCursor")
            result.next_cursor = cursor or None
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in cursors:
                raise ProviderError("PAGINATION_LOOP")
            cursors.add(cursor)
        result.total = len(result.records)
        result.incomplete = bool(result.next_cursor)
        return result
