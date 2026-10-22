"use client";

import { ApiError, api } from "@/lib/api";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const LLM_PRESETS = [
  { value: "siliconflow", label: "硅基流动", url: "https://api.siliconflow.cn/v1", model: "Qwen/Qwen3.5-35B-A3B", signup: "https://siliconflow.cn" },
  { value: "deepseek", label: "DeepSeek", url: "https://api.deepseek.com/v1", model: "deepseek-chat", signup: "https://platform.deepseek.com" },
  { value: "custom", label: "其他 / 自定义", url: "", model: "", signup: "" },
] as const;

const PUSH_CHANNELS = [
  { value: "bark", label: "Bark（iOS）", hint: "https://api.day.app/你的Key" },
  { value: "pushplus", label: "PushPlus（微信）", hint: "https://www.pushplus.plus/send/你的Token" },
  { value: "wecom_webhook", label: "企微群机器人", hint: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." },
] as const;

/** 设置页：模型配置 + 推送通道 + 演示时钟 + 退出。 */
export default function SettingsPage() {
  const router = useRouter();

  // 模型配置（用户自带服务商密钥，加密落库）
  const [baseUrl, setBaseUrl] = useState("https://api.siliconflow.cn/v1");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("Qwen/Qwen3.5-35B-A3B");
  const [masked, setMasked] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [activePreset, setActivePreset] = useState<string>("siliconflow");
  // 已配置态：显示 ✓ 摘要 +「修改」入口（用户能一眼确认配好了没）
  const [llmReady, setLlmReady] = useState(false);
  const [editLlm, setEditLlm] = useState(false);

  // 推送
  const [pushChannel, setPushChannel] = useState<string>("bark");
  const [pushEndpoint, setPushEndpoint] = useState("");
  const [pushEnabled, setPushEnabled] = useState(true);
  const [pushTestResult, setPushTestResult] = useState("");
  const [sending, setSending] = useState(false);
  const [editPush, setEditPush] = useState(false); // 已配置时收起表单，点「修改」展开

  const [error, setError] = useState("");

  // 演示时钟（GC_DEMO_MODE 时后端返回状态，否则 404 → null 不显示该区块）
  const [clock, setClock] = useState<{ today: string; override: string | null } | null>(null);
  const [jumping, setJumping] = useState(false);

  async function jump(days: number) {
    setJumping(true);
    try {
      if (days === 0) {
        setClock(await api.advanceDemoClock({ reset: true }));
      } else {
        setClock(await api.advanceDemoClock({ advance_days: days }));
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "时间快进失败");
    } finally {
      setJumping(false);
    }
  }

  useEffect(() => {
    api.getDemoClock().then(setClock).catch(() => null); // 404=未开演示模式，静默隐藏
    api
      .getLLMSettings()
      .then((settings) => {
        if (settings) {
          setBaseUrl(settings.base_url);
          setModelName(settings.model_name);
          setMasked(settings.api_key_masked);
          setLlmReady(true); // 已配置 → 显示 ✓ 摘要态
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
      setLlmReady(true);
      setEditLlm(false); // 保存成功回到 ✓ 已配置态
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "保存失败");
    }
  }

  /** 已配置态的"重新验证"：不重贴密钥，用库里配置按教练同款形态真调一次。 */
  async function verifyOnly() {
    setLlmTesting(true);
    setLlmTestResult("验证中…");
    try {
      await api.verifyLLMSettings();
      setLlmTestResult("验证通过 ✅ 模型可正常使用");
    } catch (exc) {
      setLlmTestResult(exc instanceof Error ? `验证未通过：${exc.message}` : "验证失败");
    } finally {
      setLlmTesting(false);
    }
  }

  async function saveAndTestLLM() {
    setLlmTesting(true);
    setLlmTestResult("保存并验证中…");
    setError("");
    try {
      const out = await api.saveLLMSettings({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        model_name: modelName.trim(),
      });
      setMasked(out.api_key_masked);
      // 后端按教练链路同款形态（带 tools）真实调一次——
      // 通过 = 密钥有效 + 模型存在 + 支持函数调用，与实际使用口径一致
      await api.verifyLLMSettings();
      setLlmTestResult("已保存并验证通过 ✅");
      setApiKey("");
      setLlmReady(true);
      setEditLlm(false);
    } catch (exc) {
      setLlmTestResult(
        exc instanceof ApiError && exc.status === 502
          ? `已保存，但验证未通过：${exc.message}`
          : exc instanceof Error
            ? `验证失败：${exc.message}`
            : "验证失败，请稍后重试",
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
      setEditPush(false); // 保存成功回到 ✓ 已配置态
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
      setEditPush(false);
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

      {/* 演示时间快进：仅后端 GC_DEMO_MODE=true 时出现（探测 404 即隐藏），置顶方便演示时一眼找到 */}
      {clock && (
        <section>
          <h2 className="mb-1 px-1 text-sm font-medium text-gc-muted">⏩ 演示时间快进</h2>
          <p className="mb-2 px-1 text-xs text-gc-muted">
            面试演示用：快进后今日任务/连续打卡/统计整体穿越；重启后端即恢复真实时间
          </p>
          <div className="gc-card flex flex-col gap-3 px-5 py-4">
            <p className="text-sm">
              系统的「今天」：
              <span className="font-medium">{clock.today}</span>
              {clock.override ? "（已穿越）" : "（真实时间）"}
            </p>
            <div className="flex gap-2">
              {[
                { label: "+1 天", days: 1 },
                { label: "+7 天", days: 7 },
              ].map((btn) => (
                <button
                  key={btn.label}
                  onClick={() => jump(btn.days)}
                  disabled={jumping}
                  className="flex-1 rounded-full bg-gc-accent-soft px-3 py-2 text-xs text-gc-text active:opacity-70 disabled:opacity-50"
                >
                  {btn.label}
                </button>
              ))}
              {clock.override && (
                <button
                  onClick={() => jump(0)}
                  disabled={jumping}
                  className="flex-1 rounded-full bg-gc-bg px-3 py-2 text-xs text-gc-muted active:opacity-70 disabled:opacity-50"
                >
                  回到真实
                </button>
              )}
            </div>
            <p className="text-xs text-gc-muted">快进后去「今日」页看任务滚动与连续天数累积</p>
          </div>
        </section>
      )}

    {/* 模型配置（AI 功能的前提）：已配置显示 ✓ 摘要，未配置或编辑中显示表单 */}
    <section>
      <h2 className="mb-1 px-1 text-sm font-medium text-gc-muted">
        模型配置{llmReady && !editLlm ? " ✓" : ""}
      </h2>
      {llmReady && !editLlm ? (
        <div className="gc-card flex flex-col gap-3 px-5 py-4">
          <p className="text-sm">
            ✓ 已配置——AI 功能就绪
          </p>
          <p className="text-xs leading-5 text-gc-muted">
            当前模型：{modelName}
            <br />
            密钥已加密保存，不用重复填写
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={verifyOnly}
              disabled={llmTesting}
              className="flex-1 rounded-full bg-gc-accent-soft px-3 py-2 text-xs text-gc-text active:opacity-70 disabled:opacity-50"
            >
              {llmTesting ? "验证中…" : "重新验证"}
            </button>
            <button
              type="button"
              onClick={() => setEditLlm(true)}
              className="flex-1 rounded-full bg-gc-bg px-3 py-2 text-xs text-gc-muted active:opacity-70"
            >
              修改配置
            </button>
          </div>
          {llmTestResult && <p className="text-center text-xs text-gc-muted">{llmTestResult}</p>}
        </div>
      ) : (
        <>
      <p className="mb-3 px-1 text-xs text-gc-muted">
        {editLlm
          ? "重新粘贴密钥保存即可，或点「保存」下方的返回"
          : "AI 功能需要一个对话大模型。选服务商、粘贴密钥就完成——密钥加密存在你自己的数据库里"}
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
        {editLlm && (
          <button
            type="button"
            onClick={() => setEditLlm(false)}
            className="self-center text-xs text-gc-muted underline"
          >
            返回（不改了）
          </button>
        )}
        </form>
        </>
      )}
      </section>

      {/* 推送通道：已配置显示 ✓ 摘要 */}
      <section>
        <h2 className="mb-1 px-1 text-sm font-medium text-gc-muted">
          推送通道{pushEndpoint && !editPush ? " ✓" : ""}
        </h2>
        {pushEndpoint && !editPush ? (
          <div className="gc-card flex flex-col gap-3 px-5 py-4">
            <p className="text-sm">
              ✓ 已配置{pushEnabled ? "——晨间摘要、晚间提醒、周报会推送到：" : "（当前已暂停推送）"}
            </p>
            <p className="truncate text-xs text-gc-muted">
              {PUSH_CHANNELS.find((c) => c.value === pushChannel)?.label ?? pushChannel}
              {" · "}
              {pushEndpoint}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setEditPush(true)}
                className="flex-1 rounded-full bg-gc-bg px-3 py-2 text-xs text-gc-muted active:opacity-70"
              >
                修改推送配置
              </button>
            </div>
          </div>
        ) : (
          <>
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
          {editPush && (
            <button
              type="button"
              onClick={() => setEditPush(false)}
              className="self-center text-xs text-gc-muted underline"
            >
              返回（不改了）
            </button>
          )}
        </form>
        </>
      )}
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
