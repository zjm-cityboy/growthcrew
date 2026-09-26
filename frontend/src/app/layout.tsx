import type { Metadata, Viewport } from "next";
import BottomTabs from "@/components/BottomTabs";
import ClientInit from "@/components/ClientInit";
import "./globals.css";

export const metadata: Metadata = {
  title: "成长小队 GrowthCrew",
  description: "贴入你的计划，AI 排进每天并盯着你执行",
  applicationName: "成长小队",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FDFCF8" },
    { media: "(prefers-color-scheme: dark)", color: "#1C1917" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full">
        <ClientInit />
        <main className="mx-auto min-h-dvh max-w-[480px] px-4 pb-28 pt-6">{children}</main>
        <BottomTabs />
      </body>
    </html>
  );
}
