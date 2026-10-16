"use client";

import { useEffect, useState } from "react";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const healthUrl = `${apiBaseUrl.replace(/\/$/, "")}/api/v1/health`;

type HealthPayload = {
  status: "ok" | "degraded";
  dependencies: { database: { status: "healthy" | "unhealthy" } };
  request_id: string;
  error?: { code: string; message: string };
};

type CheckState = {
  phase: "loading" | "healthy" | "database_unhealthy" | "unreachable";
  checkedAt: string | null;
  requestId: string | null;
  message: string;
};

function isHealthPayload(value: unknown): value is HealthPayload {
  if (typeof value !== "object" || value === null) return false;
  const data = value as Partial<HealthPayload>;
  return (
    typeof data.request_id === "string" &&
    (data.status === "ok" || data.status === "degraded") &&
    (data.dependencies?.database?.status === "healthy" ||
      data.dependencies?.database?.status === "unhealthy")
  );
}

export default function HealthPanel() {
  const [checkCount, setCheckCount] = useState(0);
  const [state, setState] = useState<CheckState>({
    phase: "loading",
    checkedAt: null,
    requestId: null,
    message: "",
  });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    // 覆盖后端允许的最长 10 秒检查，同时为不可达请求设置上限。
    const timer = window.setTimeout(() => controller.abort(), 12_000);

    async function check() {
      let requestId: string | null = null;
      try {
        const response = await fetch(healthUrl, {
          signal: controller.signal,
          cache: "no-store",
          headers: { Accept: "application/json" },
        });
        requestId = response.headers.get("X-Request-ID");
        const data: unknown = await response.json();
        if (!isHealthPayload(data)) throw new Error("Invalid health response");

        const healthy =
          response.status === 200 &&
          data.status === "ok" &&
          data.dependencies.database.status === "healthy";
        const databaseUnhealthy =
          response.status === 503 &&
          data.status === "degraded" &&
          data.dependencies.database.status === "unhealthy" &&
          data.error?.code === "DATABASE_UNAVAILABLE" &&
          typeof data.error.message === "string";
        if (!healthy && !databaseUnhealthy) throw new Error("Unexpected health status");

        if (active) {
          setState({
            phase: healthy ? "healthy" : "database_unhealthy",
            checkedAt: new Date().toISOString(),
            requestId: data.request_id,
            message: healthy ? "后端与数据库均可访问。" : data.error!.message,
          });
        }
      } catch {
        if (active) {
          setState({
            phase: "unreachable",
            checkedAt: new Date().toISOString(),
            requestId,
            message: requestId
              ? "后端请求未成功，请使用请求 ID 查看服务日志。"
              : "请求失败或超时，请检查后端服务、API 地址和网络连接。",
          });
        }
      } finally {
        window.clearTimeout(timer);
      }
    }

    void check();
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [checkCount]);

  const loading = state.phase === "loading";
  const titles = {
    loading: "检查中…",
    healthy: "全部正常",
    database_unhealthy: "数据库异常",
    unreachable: state.requestId ? "后端请求失败" : "无法连接后端",
  };
  const backendStatus = loading
    ? "检查中…"
    : state.phase === "unreachable"
      ? state.requestId ? "请求失败" : "不可访问"
      : "已连接";
  const databaseStatus = {
    loading: "检查中…",
    healthy: "正常",
    database_unhealthy: "异常",
    unreachable: "未知",
  };

  function recheck() {
    setState((previous) => ({ ...previous, phase: "loading", requestId: null, message: "" }));
    setCheckCount((previous) => previous + 1);
  }

  return (
    <section className={`health-card ${state.phase}`} aria-label="服务健康状态">
      <div className="status-row">
        <p className="overall-status" role="status" data-testid="overall-status">
          {titles[state.phase]}
        </p>
        <button type="button" onClick={recheck} disabled={loading}>
          {loading ? "检查中…" : "重新检查"}
        </button>
      </div>
      <p className="status-description">
        {loading ? "正在检查后端和数据库，请稍候。" : state.message}
      </p>

      <dl className="health-details">
        <div><dt>后端连接</dt><dd data-testid="backend-status">{backendStatus}</dd></div>
        <div><dt>数据库</dt><dd data-testid="database-status">{databaseStatus[state.phase]}</dd></div>
        <div>
          <dt>最近检查</dt>
          <dd data-testid="checked-at">
            {state.checkedAt ? (
              <time dateTime={state.checkedAt}>
                {new Date(state.checkedAt).toLocaleString("zh-CN", { hour12: false })}
              </time>
            ) : "尚未检查"}
          </dd>
        </div>
        <div><dt>请求 ID</dt><dd><code data-testid="request-id">{state.requestId ?? "—"}</code></dd></div>
      </dl>
      <p className="endpoint">检查地址 <code>{healthUrl}</code></p>
    </section>
  );
}
