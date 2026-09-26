"use client";

import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const LLM_PRESETS = [
  { value: "siliconflow", label: "硅基流动", url: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen3.5-35B", signup: "https://siliconflow.cn" },
  { value: "deepseek", label: "DeepSeek", url: "https://api.deepseek.com/v1", model: "deepseek-chat", signup: "https://platform.deepseek.com" },
  { value: "custom", label: "其他 / 自定义", url: "", model: "", signup: "" },
] as const;

const PUSH_CHANNELS = [
  { value: "bark", label: "Bark（iOS）", hint: "https://api.day.app/你的Key" },
  { value: "pushplus", label: "PushPlus（微信）", hint: "https://www.pushplus.plus/send/你的Token" },
  { value: "wecom_webhook", label: "企微群机器人", hint: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." },
] as const;

/** 设置页：BYOK 三件套 + 推送通道 + 退出。 */
export default function SettingsPage() {
  const router = useRouter();

  // BYOK
  const [baseUrl, setBaseUrl] = useState("https://api.siliconflow.cn/v1");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("Qwen/Qwen3.5-35B");
  const [masked, setMasked] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [activePreset, setActivePreset] = useState<string>("siliconflow");

  // 推送
  const [pushChannel, setPushChannel] = useState<string>("bark");
  const [pushEndpoint, setPushEndpoint] = useState("");
  const [pushEnabled, setPushEnabled] = useState(true);
  const [pushTestResult, setPushTestResult] = useState("");
  const [sending, setSending] = useState(false);

  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getLLMSettings()
      .then((settings) => {
        if (settings) {
          setBaseUrl(settings.base_url);
          setModelName(settings.model_name);
          setMasked(settings.api_key_masked);
        }
      })
      .catch(() => {});
    api
      .getPushSettings()
      .then((push) => {
        if (push) {
          setPushChannel(push.channel);
          setPushEndpoint(push.endpoint);
          setPushEnabled(push.enabled);
        }
      })
      .catch(() => {});
  }, []);

  const [llmTestResult, setLlmTestResult] = useState("");
  const [llmTesting, setLlmTesting] = useState(false);

  async function saveLLM(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLlmTestResult("");
    try {
      const out = await api.saveLLMSettings({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model_name: modelName.trim(),
      });
      setMasked(out.api_key_masked);
      setApiKey("");
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    }
  }

  async function saveAndTestLLM() {
    setLlmTesting(true);
    setLlmTestResult("保存并验证中…");
    setError("");
    try {
      await api.saveLLMSettings({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model_name: modelName.trim(),
      });
      // 用保存的配置发一次最小验证请求
      const testResp = await fetch(
        `${baseUrl.trim()}/chat/completions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${apiKey.trim()}`,
          },
          body: JSON.stringify({
            model: modelName.trim(),
            messages: [{ role: "user", content: "hi" }],
            max_tokens: 1,
          }),
        },
      );
      if (testResp.ok) {
        setLlmTestResult("已保存并验证通过 ✅");
        setMasked(apiKey.trim().slice(0, 3) + "***" + apiKey.trim().slice(-4));
        setApiKey("");
      } else {
        const body = await testResp.json().catch(() => ({}));
        const msg = body?.error?.message ?? `验证失败（${testResp.status}）`;
        setLlmTestResult(`已保存，但验证未通过：${msg}`);
      }
    } catch (exc) {
      setLlmTestResult(
        exc instanceof Error ? `网络错误：${exc.message}` : "验证失败，请检查网络",
      );
    } finally {
      setLlmTesting(false);
    }
  }

  async function savePush(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPushTestResult("");
    try {
      await api.savePushSettings({
        channel: pushChannel,
        endpoint: pushEndpoint.trim(),
        enabled: pushEnabled,
      });
      setPushTestResult("已保存 ✅");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    }
  }

  async function saveAndTestPush() {
    setPushTestResult("保存并发送中…");
    setSending(true);
    try {
      await api.savePushSettings({
        channel: pushChannel,
        endpoint: pushEndpoint.trim(),
        enabled: pushEnabled,
      });
      const result = await api.testPush();
      setPushTestResult(
        result.delivered ? "已保存并送达 ✅" : `已保存，但测试失败：${result.message}`,
      );
    } catch (exc) {
      setPushTestResult(exc instanceof Error ? exc.message : "操作失败");
    } finally {
      setSending(false);
    }
  }

  function logout() {
    api.logout();
    router.replace("/login");
  }

  const channelHint = PUSH_CHANNELS.find((c) => c.value === pushChannel)?.hint ?? "";

  return (
    <div className="flex flex-col gap-6">
      <header className="pt-1">
        <h1 className="text-[26px] font-medium tracking-tight">设置</h1>
      </header>

    {/* BYOK */}
    <section>
      <h2 className="mb-1 px-1 text-sm font-medium text-gc-muted">模型（BYOK）</h2>
      <p className="mb-3 px-1 text-xs text-gc-muted">
        选一个服务商，粘贴密钥就完成——密钥只加密存在你自己的库里
      </p>
      <form onSubmit={saveLLM} className="gc-card flex flex-col gap-3 px-5 py-5">
        {/* 预设服务商：一键填 URL + 模型名，用户只需贴 Key */}
        <div>
          <p className="mb-2 text-xs text-gc-muted">① 选服务商</p>
          <div className="grid grid-cols-2 gap-2">
            {LLM_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={() => {
                  setBaseUrl(preset.url);
                  setModelName(preset.model);
                  setActivePreset(preset.value);
                }}
                className={`rounded-2xl px-3 py-3 text-xs transition-colors ${
                  activePreset === preset.value
                    ? "bg-gc-accent-soft text-gc-text"
                    : "border border-gc-divider text-gc-muted"
                }`}
              >
                {preset.label}
                <span className="mt-0.5 block text-[10px] opacity-60">{preset.model}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ② 只需贴 Key（URL 和模型名已被预设填好） */}
        <label className="text-xs text-gc-muted">
          ② 粘贴 API 密钥（{activePreset === "custom" ? "自定义模式" : "从服务商后台复制"}）
          {masked && <span className="ml-1 text-gc-accent">（当前 {masked}）</span>}
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            required
            minLength={8}
            placeholder="sk-…"
            autoFocus={activePreset !== "custom"}
            className="mt-1 w-full rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none placeholder:text-gc-muted"
          />
        </label>

        {/* 注册引导链接（PM #1：新用户不知道去哪拿密钥） */}
        {activePreset !== "custom" && LLM_PRESETS.find((p) => p.value === activePreset)?.signup && (
          <a
            href={LLM_PRESETS.find((p) => p.value === activePreset)?.signup}
            target="_blank"
            rel="noopener noreferrer"
            className="-mt-1 text-[11px] text-gc-accent underline"
          >
            还没有密钥？点此免费注册（约 1 分钟）→
          </a>
        )}

        {/* 高级：自定义 Base URL / 模型名（预设选完后自动填好，通常不用动） */}
        {activePreset === "custom" ? (
          <>
            <label className="text-xs text-gc-muted">
              Base URL
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                required
                pattern="https?://.+"
                className="mt-1 w-full rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none"
              />
            </label>
            <label className="text-xs text-gc-muted">
              模型名
              <input
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                required
                className="mt-1 w-full rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none"
              />
            </label>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setActivePreset("custom")}
            className="self-start text-[10px] text-gc-muted underline"
          >
            高级设置（自定义 URL / 模型）
          </button>
        )}
        <div className="flex gap-2">
          <button
            type="submit"
            className="flex-1 rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98]"
          >
            {saved ? "已保存 ✅" : "保存"}
          </button>
          <button
            type="button"
            onClick={saveAndTestLLM}
            disabled={llmTesting || !apiKey.trim()}
            className="flex-1 rounded-full border border-gc-divider py-3 text-sm active:scale-[0.98] disabled:opacity-50"
          >
            {llmTesting ? "验证中…" : "保存并验证"}
          </button>
        </div>
        {llmTestResult && (
          <p className="text-center text-xs text-gc-muted">{llmTestResult}</p>
        )}
        </form>
      </section>

      {/* 推送 */}
      <section>
        <h2 className="mb-1 px-1 text-sm font-medium text-gc-muted">推送通道</h2>
        <p className="mb-3 px-1 text-xs text-gc-muted">
          配置后，晨间摘要、晚间提醒、周报都会推送到你指定的通道
        </p>
        <form onSubmit={savePush} className="gc-card flex flex-col gap-3 px-5 py-5">
          <div className="grid grid-cols-3 gap-2">
            {PUSH_CHANNELS.map((ch) => (
              <button
                key={ch.value}
                type="button"
                onClick={() => {
                  setPushChannel(ch.value);
                  setPushEndpoint("");
                }}
                className={`rounded-2xl px-2 py-3 text-xs transition-colors ${
                  pushChannel === ch.value
                    ? "bg-gc-accent-soft text-gc-text"
                    : "border border-gc-divider text-gc-muted"
                }`}
              >
                {ch.label}
              </button>
            ))}
          </div>
          <label className="text-xs text-gc-muted">
            端点 URL
            <input
              value={pushEndpoint}
              onChange={(e) => setPushEndpoint(e.target.value)}
              required
              minLength={10}
              pattern="https?://.+"
              placeholder={channelHint}
              className="mt-1 w-full rounded-full bg-gc-bg px-4 py-2.5 text-sm outline-none placeholder:text-gc-muted"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-gc-muted">
            <input
              type="checkbox"
              checked={pushEnabled}
              onChange={(e) => setPushEnabled(e.target.checked)}
              className="h-4 w-4 accent-[var(--gc-accent)]"
            />
            启用推送
          </label>
          <div className="flex gap-3">
            <button
              type="submit"
              className="flex-1 rounded-full bg-gc-accent py-3 text-sm text-white active:scale-[0.98]"
            >
              保存推送配置
            </button>
            <button
              type="button"
              onClick={saveAndTestPush}
              disabled={sending}
              className="flex-1 rounded-full border border-gc-divider py-3 text-sm active:scale-[0.98] disabled:opacity-60"
            >
              {sending ? "发送中…" : "保存并发测试"}
            </button>
          </div>
          {pushTestResult && (
            <p className="text-center text-xs text-gc-muted">{pushTestResult}</p>
          )}
        </form>
      </section>

      {error && (
        <p className="rounded-2xl bg-gc-peach-soft px-4 py-2.5 text-xs text-gc-text">{error}</p>
      )}

      <button onClick={logout} className="px-1 text-xs text-gc-muted underline">
        退出登录
      </button>
    </div>
  );
}
