"""连接真实前后端；不同故障由外部停止本项目服务触发，不伪造响应。"""

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.e2e


def test_real_health_page():
    scenario = os.getenv("HEALTH_SCENARIO", "healthy")
    assert scenario in {"healthy", "database_unhealthy", "unreachable"}
    web_url = os.getenv("E2E_WEB_URL", "http://localhost:3000")
    api_url = os.getenv("E2E_API_URL", "http://localhost:8000")
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)

    with sync_playwright() as playwright:
        launch_options = {"headless": True}
        if channel := os.getenv("PLAYWRIGHT_CHANNEL"):
            launch_options["channel"] = channel
        browser = playwright.chromium.launch(**launch_options)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(web_url, wait_until="networkidle")
        expect(page.get_by_role("heading", name="工程健康检查")).to_be_visible()

        if scenario == "unreachable":
            expect(page.get_by_test_id("overall-status")).to_have_text(
                "无法连接后端", timeout=15000
            )
            expect(page.get_by_test_id("backend-status")).to_have_text("不可访问")
            expect(page.get_by_test_id("database-status")).to_have_text("未知")
        else:
            expected_http = 200 if scenario == "healthy" else 503
            response = page.request.get(f"{api_url}/api/v1/health")
            assert response.status == expected_http
            expected_status = "全部正常" if scenario == "healthy" else "数据库异常"
            expected_database = "正常" if scenario == "healthy" else "异常"
            expect(page.get_by_test_id("overall-status")).to_have_text(expected_status)
            expect(page.get_by_test_id("backend-status")).to_have_text("已连接")
            expect(page.get_by_test_id("database-status")).to_have_text(expected_database)
            expect(page.get_by_test_id("request-id")).to_have_text(re.compile(r"[a-f0-9-]{36}"))

        expect(page.get_by_test_id("checked-at")).not_to_have_text("尚未检查")
        if scenario == "unreachable":
            with page.expect_request(f"{api_url}/api/v1/health"):
                page.get_by_role("button", name="重新检查").click()
        else:
            old_request_id = page.get_by_test_id("request-id").inner_text()
            with page.expect_response(f"{api_url}/api/v1/health") as latest:
                page.get_by_role("button", name="重新检查").click()
            assert latest.value.status == expected_http
            payload = latest.value.json()
            expect(page.get_by_test_id("request-id")).to_have_text(payload["request_id"])
            assert payload["request_id"] == latest.value.headers["x-request-id"]
            assert payload["request_id"] != old_request_id
        expect(page.get_by_role("button", name="重新检查")).to_be_enabled(timeout=15000)
        page.screenshot(path=str(artifacts / f"health-{scenario}.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 812})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(artifacts / f"health-{scenario}-mobile.png"), full_page=True)
        browser.close()


def test_loading_state_until_the_real_request_continues():
    """只暂缓传输以观察进行中状态；放行后仍请求真实 API，不伪造响应。"""
    with sync_playwright() as playwright:
        options = {"headless": True}
        if channel := os.getenv("PLAYWRIGHT_CHANNEL"):
            options["channel"] = channel
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        pending = []
        page.route("**/api/v1/health", lambda route: pending.append(route))
        with page.expect_request("**/api/v1/health"):
            page.goto(
                os.getenv("E2E_WEB_URL", "http://localhost:3000"), wait_until="domcontentloaded"
            )

        expect(page.get_by_test_id("overall-status")).to_have_text("检查中…")
        expect(page.get_by_role("button", name="检查中…")).to_be_disabled()
        page.screenshot(path="artifacts/health-loading.png", full_page=True)
        for route in pending:
            route.continue_()
        expect(page.get_by_role("button", name="重新检查")).to_be_enabled(timeout=15000)
        browser.close()
