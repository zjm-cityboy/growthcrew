"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/", label: "今日", icon: "☀️" },
  { href: "/chat", label: "对话", icon: "💬" },
  { href: "/archive", label: "档案", icon: "📖" },
];

/** 底部浮动药丸 Tab 栏（设计系统：70% 白底 + 毛玻璃 + 24px 圆角悬浮）。 */
export default function BottomTabs() {
  const pathname = usePathname();
  // 登录页和子页面不显示主导航
  if (pathname === "/login" || pathname.startsWith("/archive/reports")) return null;
  return (
    <nav
      aria-label="主导航"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-[448px] items-center justify-around rounded-3xl bg-gc-card/70 px-2 py-2 backdrop-blur-xl"
      style={{ boxShadow: "var(--gc-shadow-float)" }}
    >
      {TABS.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`flex min-w-16 flex-col items-center gap-0.5 rounded-2xl px-4 py-1.5 text-xs transition-colors ${
              active ? "text-gc-accent" : "text-gc-muted"
            }`}
          >
            <span className="text-lg leading-none">{tab.icon}</span>
            <span className="relative">
              {tab.label}
              {active && (
                <span className="absolute -top-1 left-1/2 h-1 w-1 -translate-x-1/2 rounded-full bg-gc-accent" />
              )}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
