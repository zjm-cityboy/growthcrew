# Theme Tokens

## Part 1 — 紧凑令牌摘要（优先作为上下文传递）

- **CSS 方案**：Tailwind CSS v4（`@import "tailwindcss"` + `@theme inline`，无 tailwind.config 文件）
- **颜色**（脚手架默认，仅 2 个令牌，设计系统将扩展）：
  - 亮色：`--background: #ffffff`；`--foreground: #171717`
  - 暗色（`prefers-color-scheme: dark`）：`--background: #0a0a0a`；`--foreground: #ededed`
- **字体**：
  - Sans：Geist（`--font-geist-sans`，next/font 注入；中文场景需补中文字体栈）
  - Mono：Geist Mono（`--font-geist-mono`）
- **暗色模式**：跟随系统 `prefers-color-scheme`（规划：+ 手动切换）
- **间距/圆角/阴影/断点**：Tailwind v4 默认刻度，无自定义
- **设计系统**：见 `.superdesign/design-system.md`（真正的视觉规范所在）

## Part 2 — 原始文件

### `frontend/src/app/globals.css`（全文）

```css
@import "tailwindcss";

:root {
  --background: #ffffff;
  --foreground: #171717;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #0a0a0a;
    --foreground: #ededed;
  }
}

body {
  background: var(--background);
  color: var(--foreground);
  font-family: Arial, Helvetica, sans-serif;
}
```

> Tailwind v4 无 tailwind.config.*；主题经 `@theme` CSS 指令定义。
