"use client";

/** 从 CSS 变量读设计令牌值，供 ECharts option 使用（暗色模式适配，P3.4）。
 *
 * ECharts 的 SVG renderer 不解析 var()，需要读取计算后的具体色值。
 * 主题切换后需刷新页面才能生效（可接受——主题切换是低频操作）。
 */

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function chartColors() {
  return {
    accent: cssVar("--gc-accent", "#5C8A6E"),
    accentSoft: cssVar("--gc-accent-soft", "#E8EFE8"),
    muted: cssVar("--gc-muted", "#78716C"),
    peach: cssVar("--gc-peach", "#FFB7B2"),
    divider: cssVar("--gc-divider", "#E7E5E4"),
    bg: cssVar("--gc-bg", "#FDFCF8"),
    card: cssVar("--gc-card", "#FFFFFF"),
  };
}
