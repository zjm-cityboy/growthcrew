import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Next.js Turbopack 禁用同步对话框 API——用状态提示或 MiniSheet 替代
      "no-restricted-syntax": [
        "error",
        {
          selector: "CallExpression[callee.object.name='window'][callee.property.name='prompt']",
          message: "window.prompt() 在 Next.js Turbopack 下不可用。用内联输入框或 MiniSheet 替代。",
        },
        {
          selector: "CallExpression[callee.object.name='window'][callee.property.name='alert']",
          message: "window.alert() 在 Next.js Turbopack 下不可用。用 setError() 或通知组件替代。",
        },
        {
          selector: "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
          message: "window.confirm() 在 Next.js Turbopack 下不可用。用 MiniSheet 确认框替代。",
        },
        // 裸调用也拦
        {
          selector: "CallExpression[callee.name='alert']",
          message: "alert() 在 Next.js Turbopack 下不可用。用 setError() 或通知组件替代。",
        },
        {
          selector: "CallExpression[callee.name='confirm']",
          message: "confirm() 在 Next.js Turbopack 下不可用。用 MiniSheet 确认框替代。",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
