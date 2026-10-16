"use client";

import { useEffect, useState } from "react";
import { isDemoCatalog, type CatalogState } from "./catalog-types";

export function useDemoCatalog() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<CatalogState>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => controller.abort(), 5_000);
    async function read() {
      try {
        const response = await fetch("/demo/catalog.json", { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Catalog unavailable");
        const catalog: unknown = await response.json();
        if (!isDemoCatalog(catalog)) throw new Error("Invalid demo catalog");
        if (active) setState({ phase: "ready", catalog });
      } catch {
        if (active) setState({ phase: "error" });
      } finally {
        window.clearTimeout(timer);
      }
    }
    void read();
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [attempt]);

  function retry() {
    setState({ phase: "loading" });
    setAttempt((previous) => previous + 1);
  }

  return { state, retry };
}
