"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function SiteHeader() {
  const pathname = usePathname();
  const links = [
    { href: "/discover", label: "发现工具", active: pathname === "/discover" || pathname.startsWith("/tools/") },
    { href: "/assistant", label: "选型助手", active: pathname === "/assistant" },
    { href: "/status", label: "工程状态", active: pathname === "/status" },
  ];
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link className="brand" href="/discover" aria-label="AgentRadar · 发现工具">
          <svg viewBox="0 0 40 40" width="36" height="36" aria-hidden="true" fill="none">
            <rect width="40" height="40" rx="12" fill="currentColor" />
            <g className="brand-radar" stroke="currentColor" strokeWidth="1.5">
              <circle cx="20" cy="20" r="12" /><circle cx="20" cy="20" r="6" />
              <path d="M20 20 29 11M20 8v12H8" /><circle cx="26" cy="14" r="2.5" fill="currentColor" />
            </g>
          </svg>
          <span translate="no">AgentRadar</span>
        </Link>
        <nav className="site-nav" aria-label="主要导航">
          {links.map((link) => (
            <Link key={link.href} href={link.href} aria-current={link.active ? "page" : undefined}>
              {link.label}
            </Link>
          ))}
        </nav>
        <span className="prototype-label">P01 产品原型</span>
      </div>
    </header>
  );
}
