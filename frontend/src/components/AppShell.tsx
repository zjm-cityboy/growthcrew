"use client";

import BottomTabs from "@/components/BottomTabs";
import { usePathname } from "next/navigation";

/** 全局壳：用户端=手机窄屏+底部导航；/admin=桌面全宽（独立管理端布局）。 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname.startsWith("/admin")) {
    return <div className="min-h-dvh">{children}</div>;
  }
  return (
    <>
      <main className="mx-auto min-h-dvh max-w-[480px] px-4 pb-28 pt-6">{children}</main>
      <BottomTabs />
    </>
  );
}
