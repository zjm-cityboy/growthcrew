"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

/** 管理端独立布局：桌面侧边栏形态，不复用用户端手机壳与底部导航。 */

const NAV = [
  { href: "/admin", label: "系统总览", icon: "📊" },
  { href: "/admin/users", label: "用户管理", icon: "👥" },
  { href: "/admin/goals", label: "目标管理", icon: "🎯" },
  { href: "/admin/tasks", label: "任务管理", icon: "📋" },
  { href: "/admin/proposals", label: "提案审计", icon: "📝" },
  { href: "/admin/records", label: "记录管理", icon: "🗂️" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-dvh bg-gc-bg">
      <aside className="sticky top-0 flex h-dvh w-56 shrink-0 flex-col gap-1 border-r border-gc-divider px-4 py-6">
        <p className="px-2 text-base font-semibold tracking-tight">GrowthCrew</p>
        <p className="mb-4 px-2 text-xs text-gc-muted">管理后台</p>
        {NAV.map((item) => {
          const active =
            item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-xl px-3 py-2.5 text-sm transition-colors ${
                active
                  ? "bg-gc-accent-soft font-medium text-gc-text"
                  : "text-gc-muted hover:bg-gc-card"
              }`}
            >
              <span className="mr-2">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
        <div className="mt-auto flex flex-col gap-1">
          <Link
            href="/"
            className="rounded-xl px-3 py-2 text-xs text-gc-muted hover:bg-gc-card"
          >
            ← 返回用户端
          </Link>
          <p className="px-3 pt-2 text-[10px] leading-4 text-gc-muted">
            管理员由 backend/.env 的 GC_ADMIN_USERNAMES 指定
          </p>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-6">{children}</main>
    </div>
  );
}
