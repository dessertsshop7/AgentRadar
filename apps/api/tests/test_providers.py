"""仅替代外部 HTTP；测试真实 Adapter 的解析、限流、分页和网络边界。"""

import asyncio
import gzip
import json

import httpx
import pytest


def repository_payload(identity=42, name="owner/project"):
    return {
        "id": identity,
        "full_name": name,
        "html_url": f"https://github.com/{name}",
        "description": "RAG agent framework",
        "stargazers_count": 50,
        "forks_count": 3,
        "pushed_at": "2026-10-17T00:00:00Z",
        "created_at": "2025-01-01T00:00:00Z",
        "archived": False,
        "disabled": False,
        "private": False,
        "license": {"spdx_id": "MIT"},
        "topics": ["rag", "agent"],
    }


def test_compressed_response_is_not_decompressed_twice_after_size_check():
    from app.ingestion.providers import ProviderHTTP

    async def scenario():
        payload = gzip.compress(b'{"ok":true}')
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"content-encoding": "gzip"}, content=payload
                )
            ),
        ) as client:
            assert (await ProviderHTTP(client).get("/sample")).json() == {"ok": True}

    asyncio.run(scenario())


def test_github_pagination_deduplicates_and_reports_incomplete_coverage():
    from app.ingestion.providers import GitHubRepositoryAdapter

    async def scenario():
        def respond(request):
            if request.url.params.get("page") == "2":
                return httpx.Response(
                    200,
                    json={
                        "total_count": 3,
                        "incomplete_results": False,
                        "items": [repository_payload(42), repository_payload(43)],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "incomplete_results": False,
                    "items": [repository_payload()],
                },
                headers={
                    "link": '<https://api.github.com/search/repositories?q=rag&page=2>; rel="next"'
                },
            )

        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(respond)
        ) as client:
            adapter = GitHubRepositoryAdapter(client)
            found = await adapter.discover("rag", limit=100)
            assert [item["id"] for item in found.records] == [42, 43]
            assert found.pages == 2 and not found.incomplete

    asyncio.run(scenario())


def test_search_over_1000_is_reported_not_claimed_as_full_coverage():
    from app.ingestion.providers import GitHubRepositoryAdapter

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "total_count": 2000,
                        "incomplete_results": True,
                        "items": [repository_payload()],
                    },
                )
            ),
        ) as client:
            found = await GitHubRepositoryAdapter(client).discover("rag", limit=100)
            assert found.incomplete and found.total == 2000

    asyncio.run(scenario())


def test_retry_after_and_server_failure_eventually_return_real_response():
    from app.ingestion.providers import ProviderHTTP

    async def scenario():
        attempts = []

        def respond(request):
            attempts.append(request.url.path)
            if len(attempts) == 1:
                return httpx.Response(429, headers={"retry-after": "0"})
            if len(attempts) == 2:
                return httpx.Response(503)
            return httpx.Response(200, json={"ok": True})

        async def no_wait(seconds):
            return None

        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(respond)
        ) as client:
            response = await ProviderHTTP(client, sleep=no_wait).get("/sample")
            assert response.json() == {"ok": True} and len(attempts) == 3

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode,code",
    [
        ("timeout", "TIMEOUT"),
        ("forbidden", "FORBIDDEN"),
        ("rate", "RATE_LIMITED"),
        ("secondary", "RATE_LIMITED"),
        ("protocol", "NETWORK_ERROR"),
        ("oversize", "RESPONSE_TOO_LARGE"),
    ],
)
def test_failures_are_bounded_and_do_not_expose_upstream_bodies(mode, code):
    from app.ingestion.providers import ProviderError, ProviderHTTP

    async def scenario():
        def respond(request):
            if mode == "timeout":
                raise httpx.ReadTimeout("secret-sentinel", request=request)
            if mode == "forbidden":
                return httpx.Response(403, text="secret-sentinel")
            if mode == "rate":
                return httpx.Response(
                    403, headers={"x-ratelimit-remaining": "0", "retry-after": "120"}
                )
            if mode == "secondary":
                return httpx.Response(403, json={"message": "secondary rate limit exceeded"})
            if mode == "protocol":
                raise httpx.RemoteProtocolError("secret-sentinel", request=request)
            return httpx.Response(200, content=b"secret-sentinel" * 100)

        async def no_wait(seconds):
            return None

        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(respond)
        ) as client:
            with pytest.raises(ProviderError) as caught:
                await ProviderHTTP(client, max_bytes=100, sleep=no_wait).get("/sample")
            assert caught.value.code == code
            assert "secret-sentinel" not in str(caught.value)

    asyncio.run(scenario())


def test_rename_follows_only_trusted_redirect_and_preserves_repository_id():
    from app.ingestion.providers import GitHubRepositoryAdapter, ProviderError

    async def scenario():
        def respond(request):
            if request.url.path == "/repos/old/name":
                return httpx.Response(
                    301, headers={"location": "https://api.github.com/repos/new/name"}
                )
            if request.url.path == "/repos/new/name":
                return httpx.Response(200, json=repository_payload(42, "new/name"))
            return httpx.Response(301, headers={"location": "https://attacker.invalid/steal"})

        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={"Authorization": "Bearer test-only"},
            transport=httpx.MockTransport(respond),
        ) as client:
            adapter = GitHubRepositoryAdapter(client)
            repo = await adapter.repository("old/name")
            assert repo["id"] == 42 and repo["full_name"] == "new/name"
            with pytest.raises(ProviderError) as caught:
                await adapter.repository("bad/name")
            assert caught.value.code == "UNSAFE_REDIRECT"

    asyncio.run(scenario())


def test_repository_404_is_ambiguous_not_a_confirmed_deletion():
    from app.ingestion.providers import GitHubRepositoryAdapter, ProviderError

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://api.github.com",
            transport=httpx.MockTransport(lambda request: httpx.Response(404)),
        ) as client:
            with pytest.raises(ProviderError) as caught:
                await GitHubRepositoryAdapter(client).repository("owner/missing")
            assert caught.value.code == "NOT_FOUND_OR_INACCESSIBLE"

    asyncio.run(scenario())


def test_readme_304_sends_etag_and_missing_readme_is_explicit():
    from app.ingestion.providers import GitHubRepositoryAdapter

    async def scenario():
        def respond(request):
            if "/missing/" in request.url.path:
                return httpx.Response(404)
            assert request.headers["if-none-match"] == '"etag-test"'
            return httpx.Response(304)

        async with httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(respond)
        ) as client:
            adapter = GitHubRepositoryAdapter(client)
            assert (await adapter.readme("owner/repo", '"etag-test"')).status == "unchanged"
            assert (await adapter.readme("missing/repo")).status == "missing"

    asyncio.run(scenario())


def test_registry_cursor_and_non_github_server_shape():
    from app.ingestion.providers import MCPRegistryAdapter

    async def scenario():
        def respond(request):
            if request.url.params.get("cursor") == "opaque-next":
                return httpx.Response(
                    200,
                    json={
                        "servers": [
                            {
                                "server": {
                                    "name": "org.example/b",
                                    "description": "B",
                                    "version": "2",
                                }
                            }
                        ],
                        "metadata": {},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "servers": [
                        {
                            "server": {"name": "org.example/a", "description": "A", "version": "1"},
                            "_meta": {
                                "io.modelcontextprotocol.registry/official": {"status": "active"}
                            },
                        }
                    ],
                    "metadata": {"nextCursor": "opaque-next"},
                },
            )

        async with httpx.AsyncClient(
            base_url="https://registry.modelcontextprotocol.io",
            transport=httpx.MockTransport(respond),
        ) as client:
            result = await MCPRegistryAdapter(client).discover(limit=100)
            assert [row["server"]["name"] for row in result.records] == [
                "org.example/a",
                "org.example/b",
            ]
            assert result.pages == 2 and not result.incomplete

    asyncio.run(scenario())


def test_invalid_registry_envelope_is_a_recordable_schema_error():
    from app.ingestion.providers import MCPRegistryAdapter, ProviderError

    async def scenario():
        async with httpx.AsyncClient(
            base_url="https://registry.modelcontextprotocol.io",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=json.dumps({"renamed_servers": []}))
            ),
        ) as client:
            with pytest.raises(ProviderError) as caught:
                await MCPRegistryAdapter(client).discover(limit=10)
            assert caught.value.code == "SCHEMA_CHANGED"

    asyncio.run(scenario())
