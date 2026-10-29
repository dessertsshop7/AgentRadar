"""P01 浏览器验收：默认读取真实静态文件；空目录/损坏响应使用替身。

这些测试验证原型交互，不证明真实工具、推荐、模型或业务 API 可用。
"""

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright

pytestmark = pytest.mark.e2e
WEB_URL = os.getenv("E2E_WEB_URL", "http://localhost:3000").rstrip("/")


@pytest.fixture(scope="module")
def product_browser():
    with sync_playwright() as playwright:
        options = {"headless": True}
        if channel := os.getenv("PLAYWRIGHT_CHANNEL"):
            options["channel"] = channel
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


@pytest.fixture
def product_page(product_browser: Browser):
    context = product_browser.new_context(reduced_motion="reduce")
    page = context.new_page()
    yield page
    context.close()


def assert_fits_viewport(page: Page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def keyboard_to(page: Page, locator: Locator):
    """通过实际 Tab 遍历定位控件，不用脚本替代键盘操作。"""
    for _ in range(45):
        if locator.evaluate("element => element === document.activeElement"):
            return
        page.keyboard.press("Tab")
    expect(locator).to_be_focused()


def test_search_filter_empty_results_and_reset(product_page: Page):
    page = product_page
    page.goto(WEB_URL)
    expect(page).to_have_url(f"{WEB_URL}/discover")
    expect(page.get_by_role("heading", name="找到值得一试的 AI 工具")).to_be_visible()
    expect(page.get_by_test_id("demo-notice")).to_contain_text("演示数据")
    expect(page.get_by_test_id("tool-card")).to_have_count(6)
    page.get_by_label("搜索工具").fill("知识库")
    page.get_by_label("应用场景").select_option("knowledge")
    page.get_by_label("上手门槛").select_option("beginner")
    page.get_by_role("button", name="搜索与筛选", exact=True).click()
    expect(page.get_by_test_id("tool-card")).to_have_count(1)
    expect(page.get_by_role("link", name="团队知识库问答助手", exact=True)).to_be_visible()
    assert "category=knowledge" in page.url
    page.reload()
    expect(page.get_by_label("搜索工具")).to_have_value("知识库")
    expect(page.get_by_label("应用场景")).to_have_value("knowledge")
    expect(page.get_by_test_id("tool-card")).to_have_count(1)
    page.get_by_label("搜索工具").fill("不存在的工具名称123")
    page.get_by_role("button", name="搜索与筛选", exact=True).click()
    expect(page.get_by_role("heading", name="没有找到匹配的演示工具")).to_be_visible()
    page.get_by_role("link", name="清除筛选", exact=True).click()
    expect(page.get_by_test_id("tool-card")).to_have_count(6)


def test_card_action_is_a_touch_sized_navigation_link(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/discover")
    action = page.get_by_role("link", name="查看团队知识库问答助手的用途与限制", exact=True)
    expect(action).to_be_visible()
    assert action.bounding_box()["height"] >= 44
    action.click()
    expect(page).to_have_url(f"{WEB_URL}/tools/knowledge-base")
    expect(page.get_by_role("heading", name="团队知识库问答助手", exact=True)).to_be_visible()


@pytest.mark.parametrize("width", [375, 768, 1440])
def test_discover_detail_assistant_journey_at_each_width(product_page: Page, width: int):
    page = product_page
    page.set_viewport_size({"width": width, "height": 960})
    page.goto(f"{WEB_URL}/discover")
    expect(page.get_by_test_id("tool-card")).to_have_count(6)
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    assert_fits_viewport(page)
    page.screenshot(path=str(artifacts / f"p01-discover-{width}.png"), full_page=True)
    page.get_by_role("link", name="团队知识库问答助手", exact=True).click()
    expect(page.get_by_role("heading", name="团队知识库问答助手", exact=True)).to_be_visible()
    expect(page.get_by_role("heading", name="适合与不适合")).to_be_visible()
    expect(page.get_by_test_id("demo-notice")).to_contain_text("演示数据")
    assert_fits_viewport(page)
    page.screenshot(path=str(artifacts / f"p01-detail-{width}.png"), full_page=True)
    page.get_by_role("link", name="用这个场景试试选型助手").click()
    expect(page.get_by_text("正在评估：团队知识库问答助手", exact=True)).to_be_visible()
    page.get_by_label("你想解决什么问题").fill("我希望把团队文档整理成可以检索和核对来源的知识库。")
    page.get_by_label("业务场景").select_option("knowledge")
    page.get_by_label("技术条件").select_option("beginner")
    page.get_by_role("button", name="展示演示方案").click()
    expect(page.get_by_role("heading", name="你的演示选型方案")).to_be_focused()
    expect(page.get_by_test_id("assistant-result")).to_contain_text("演示交互，未连接模型")
    expect(page.get_by_test_id("assistant-result")).to_contain_text("团队知识库问答助手")
    expect(page.get_by_test_id("assistant-result")).to_contain_text("固定规则")
    assert_fits_viewport(page)
    page.screenshot(path=str(artifacts / f"p01-assistant-{width}.png"), full_page=True)
    page.get_by_role("link", name="工程状态", exact=True).click()
    expect(page.get_by_role("heading", name="工程健康检查")).to_be_visible()


def test_core_flow_can_be_completed_with_keyboard(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/discover")
    keyboard_to(page, page.get_by_role("link", name="跳到主要内容"))
    page.keyboard.press("Enter")
    search = page.get_by_label("搜索工具")
    keyboard_to(page, search)
    page.keyboard.type("knowledge")
    keyboard_to(page, page.get_by_role("button", name="搜索与筛选", exact=True))
    page.keyboard.press("Enter")
    tool = page.get_by_role("link", name="团队知识库问答助手", exact=True)
    keyboard_to(page, tool)
    assert tool.evaluate("element => getComputedStyle(element).outlineStyle !== 'none'")
    page.keyboard.press("Enter")
    keyboard_to(page, page.get_by_role("link", name="用这个场景试试选型助手"))
    page.keyboard.press("Enter")
    keyboard_to(page, page.get_by_label("你想解决什么问题"))
    page.keyboard.type("We need searchable team documentation with source references.")
    keyboard_to(page, page.get_by_role("button", name="展示演示方案"))
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", name="你的演示选型方案")).to_be_focused()


def test_assistant_rejects_blank_need_and_explains_changed_rule(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/assistant")
    submit = page.get_by_role("button", name="展示演示方案")
    expect(submit).to_be_enabled()
    page.get_by_label("你想解决什么问题").fill("          ")
    submit.click()
    expect(page.get_by_test_id("assistant-form").get_by_role("alert")).to_be_visible()
    expect(page.get_by_label("你想解决什么问题")).to_be_focused()
    expect(page.get_by_test_id("assistant-result")).to_have_count(0)
    page.get_by_label("你想解决什么问题").fill(
        "需要把多份文档转成结构化格式，并且有开发人员协助部署。"
    )
    page.get_by_label("业务场景").select_option("knowledge")
    page.get_by_label("技术条件").select_option("developer")
    submit.click()
    result = page.get_by_test_id("assistant-result")
    expect(result).to_contain_text("文档结构化处理工具箱")
    expect(result).to_contain_text("有开发支持")
    expect(result).to_contain_text("输入文本不参与语义分析")


def test_invalid_resubmission_cannot_keep_an_old_demo_result(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/assistant")
    need = page.get_by_label("你想解决什么问题")
    need.fill("需要把团队资料整理成可以核对来源的知识库。")
    page.get_by_role("button", name="展示演示方案").click()
    expect(page.get_by_test_id("assistant-result")).to_be_visible()
    need.fill("          ")
    page.get_by_role("button", name="展示演示方案").click()
    expect(page.get_by_test_id("assistant-form").get_by_role("alert")).to_be_visible()
    expect(need).to_be_focused()
    expect(page.get_by_test_id("assistant-result")).to_have_count(0)


def test_catalog_loading_failure_and_retry(product_page: Page):
    page = product_page
    pending = []
    page.route("**/demo/catalog.json", lambda route: pending.append(route))
    with page.expect_request("**/demo/catalog.json"):
        page.goto(f"{WEB_URL}/discover", wait_until="domcontentloaded")
    expect(page.get_by_role("status")).to_contain_text("正在读取演示目录")
    for route in pending:
        route.continue_()
    expect(page.get_by_test_id("tool-card")).to_have_count(6)
    page.unroute("**/demo/catalog.json")
    page.route("**/demo/catalog.json", lambda route: route.abort("failed"))
    page.reload()
    expect(page.get_by_role("alert").filter(has_text="演示目录读取失败")).to_be_visible()
    page.unroute("**/demo/catalog.json")
    page.get_by_role("button", name="重试读取").click()
    expect(page.get_by_test_id("tool-card")).to_have_count(6)


def test_empty_catalog_has_its_own_state(product_page: Page):
    """明确的响应替身，只验证空目录 UI，不算真实文件或业务数据验证。"""
    page = product_page
    page.route(
        "**/demo/catalog.json",
        lambda route: route.fulfill(
            json={
                "schema_version": 1,
                "provenance": "fictional-demo",
                "categories": [],
                "tools": [],
            }
        ),
    )
    page.goto(f"{WEB_URL}/discover")
    expect(page.get_by_role("heading", name="演示目录暂时没有内容")).to_be_visible()
    expect(page.get_by_test_id("tool-card")).to_have_count(0)


def test_malformed_catalog_is_a_recoverable_error(product_page: Page):
    page = product_page
    page.route(
        "**/demo/catalog.json",
        lambda route: route.fulfill(
            body=json.dumps({"tools": "invalid"}), content_type="application/json"
        ),
    )
    page.goto(f"{WEB_URL}/assistant")
    expect(page.get_by_role("alert").filter(has_text="演示目录读取失败")).to_be_visible()
    page.unroute("**/demo/catalog.json")
    page.get_by_role("button", name="重试读取").click()
    expect(page.get_by_role("button", name="展示演示方案")).to_be_enabled()


def test_unknown_tool_has_recovery_navigation(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/tools/not-a-demo-tool")
    expect(page.get_by_role("heading", name="没有找到这个页面或演示工具")).to_be_visible()
    page.get_by_role("link", name="返回发现页", exact=True).click()
    expect(page.get_by_test_id("tool-card")).to_have_count(6)


def test_unknown_assistant_context_has_recovery_without_inventing_a_tool(product_page: Page):
    page = product_page
    page.goto(f"{WEB_URL}/assistant?tool=unknown-p02-tool")
    expect(
        page.get_by_text("没有找到带入的演示工具，请重新选择业务场景。", exact=True)
    ).to_be_visible()
    expect(page.get_by_label("业务场景")).to_be_enabled()
    page.get_by_label("你想解决什么问题").fill("希望把团队资料整理成可以检索与核对来源的知识库。")
    page.get_by_role("button", name="展示演示方案").click()
    expect(page.get_by_test_id("assistant-result")).to_contain_text("演示交互，未连接模型")
