# GrowthCrew 成长小队 — Design System v1.0

> 风格来源：Superdesign 风格库 `softly-digital-wellness-app`（Softly — Digital Wellness App），借鉴模式：保留其"数字客厅"温暖纸感与低流速动效，强调色按产品语义替换为成长绿。
> 核心氛围：**清晨般安静、鼓励而不施压**（产品哲学：不制造焦虑）。

## 1. 产品上下文

- **产品**：GrowthCrew 成长小队 — 面向自学者的成长执行系统（手机优先 PWA，三 Tab：今日/对话/档案）
- **关键页面**：今日（晨推+打卡+生活三打卡+进展）、对话（与 AI 总编对话、审批卡）、档案（日历热力图/streak/趋势/卡因分析）
- **核心场景（JTBD）**：早晨 1 分钟内知道今天干什么；打卡路径 ≤2 步；跳过任务时一键选卡因（分心/太难/疲劳/被打断）；晚上 1 分钟轻复盘
- **克制要求**：无红色告警、无惩罚性视觉（断签不出现"失败"意象）、信息密度低（每日任务 ≤3）
- **语言**：简体中文界面；数字（streak/百分比）用 Outfit 展示其圆润感

## 2. 色彩（Color）

| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#FDFCF8` | 页面背景（暖纸白） |
| `--bg-card` | `#FFFFFF` | 卡片背景 |
| `--text-primary` | `#292524` | 主文字（软黑） |
| `--text-muted` | `#78716C` | 次要文字（石灰） |
| `--accent` | `#5C8A6E` | **成长绿**：主操作、完成态、打卡成功 |
| `--accent-soft` | `#E8EFE8` | 成长绿浅底：选中态、进度条底、Sage 场景色 |
| `--peach` | `#FFB7B2` | 蜜桃色：庆祝时刻、streak 徽章、心情（次强调，不做警示） |
| `--lavender` | `#EFEDF4` | 薰衣草底：对话/AI 相关卡片、晚间复盘场景 |
| `--divider` | `#E7E5E4` | 分隔线（stone-200） |

- 深色模式：背景 `#1C1917`（stone-900）、卡片 `#292524`、主文字 `#E7E5E4`、次要 `#A8A29E`；成长绿提亮为 `#7FB08F`；蜜桃/薰衣草降低饱和度
- **禁止**：纯红/橙警示色、高饱和渐变、深黑纯白对比

## 3. 字体（Typography）

- 主字体栈：`Outfit, "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei", system-ui, sans-serif`（Outfit 负责数字与拉丁，中文走系统栈）
- 类型刻度（App 场景，非落地页）：
  - 页面问候语/大数字：28-32px，tracking -0.02em，Medium
  - 卡片标题：17-18px，Medium
  - 正文/任务名：15-16px，Regular
  - 辅助说明：13px，`--text-muted`
  - Tab 栏/徽章：12-13px
- 句首大写规则不适用（中文）；英文句子 sentence-case

## 4. 形状与阴影（Shape & Elevation）

- 卡片圆角：24px（rounded-3xl）；小元素/输入框：full 药丸
- 底部 Tab 栏：**浮动药丸**（左右 16px 边距、70% 白底 + 20px backdrop-blur，Softly 导航的语言延续）
- 阴影（唯一的 elevation 语言，禁止重阴影）：`0 4px 20px -2px rgba(0,0,0,0.05)`
- 全局纸感颗粒：feTurbulence SVG grain，opacity 0.2，mix-blend overlay（比 Softly 的 0.35 收敛，保可读性）

## 5. 布局（Layout）

- 移动优先：页面左右 16px padding，卡片间距 12px，单列纵向流
- 内容最大宽度 480px 居中（桌面端同样式）
- 触达优先：主操作全部落拇指热区（底部 Tab、卡片右侧勾选圆圈 ≥44px）

## 6. 动效（Motion）

- 低流速：过渡 300-500ms，ease-out；无弹跳急停
- 打卡成功：勾选圆圈 scale 1→0.9→1（350ms）+ 卡片轻微变淡下沉，**不撒花不爆闪**
- 列表进场：translateY 12px→0 + 淡入（400ms，错峰 50ms）
- 空状态才允许浮动背景 blob（6s 慢循环 ±10px）

## 7. 组件规范（关键组件）

- **任务卡**：白底 24px 圆角，左任务名+时长标签，右成长绿描边勾选圆圈；完成态=绿底白勾+文字置灰；长按/点"跳过"弹卡因四选一底部抽屉（分心/太难/疲劳/被打断）
- **生活三打卡**：三个等宽药丸（😴睡眠 / 🏃运动 / 😊心情），未选=白底灰描边，已选=对应浅底（sage/peach/lavender）
- **streak 徽章**：蜜桃底圆角块 + Outfit 数字（如 "12 天"），断签后显示灰底"归因分析中…"文案，无失败图示
- **审批卡**：薰衣草底，标题+要点列表+两个药丸按钮（成长绿实心"同意"/白底描边"再想想"）
- **底部 Tab**：浮动药丸三等分（今日/对话/档案），激活项成长绿文字+顶部小圆点

## 8. 硬约束（每次生成必须遵守）

Use ONLY the fonts, colors, spacing, radius, shadows, and component styles defined in this design system. Do not introduce any fonts, colors, or visual styles not in the design system — especially no red/orange warning colors, no high-saturation gradients, no heavy shadows.
