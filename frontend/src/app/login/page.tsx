"use client";

import { api, loadTokens } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (loadTokens()) router.replace("/");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") {
        await api.login(username, password);
      } else {
        await api.register(username, password);
      }
      router.replace("/");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "出错了");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col justify-center px-2">
      <div className="gc-card px-6 py-8">
        <h1 className="text-center text-xl font-medium">成长小队</h1>
        <p className="mt-1.5 text-center text-xs text-gc-muted">
          贴入你的计划，AI 排进每天并盯着你执行
        </p>

        <form onSubmit={submit} className="mt-7 flex flex-col gap-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="用户名"
            autoComplete="username"
            required
            minLength={3}
            className="rounded-full bg-gc-bg px-5 py-3 text-sm outline-none placeholder:text-gc-muted"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="密码（至少 8 位）"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={8}
            className="rounded-full bg-gc-bg px-5 py-3 text-sm outline-none placeholder:text-gc-muted"
          />
          {error && (
            <p className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-xs text-gc-text">{error}</p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="mt-1 rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98] disabled:opacity-60"
          >
            {busy ? "请稍候…" : mode === "login" ? "登录" : "注册并登录"}
          </button>
        </form>

        <button
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="mt-4 w-full text-center text-xs text-gc-muted"
        >
          {mode === "login" ? "没有账号？注册一个" : "已有账号？直接登录"}
        </button>
      </div>
    </div>
  );
}
