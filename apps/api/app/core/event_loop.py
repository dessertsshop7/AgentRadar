import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Uvicorn 循环工厂：兼容 Windows 上的 psycopg 异步连接。"""
    return asyncio.SelectorEventLoop()
