# 08 · 前端图表与 ECharts 集成（P2.4）

> 比喻：档案页是"成长展览馆"——四张图表是展品，ChartCard 是展框，后端统计 API 是策展人提供的数据。

## 一、ECharts 按需加载（不是 `import echarts from "echarts"`）

```typescript
// 全量引入（P2-7 审查修复前）——拉入 graph/treemap/dataZoom 等数百 KB 未用模块
import ReactECharts from "echarts-for-react";

// 按需注册（修复后）——只用 BarChart + HeatmapChart
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
echarts.use([BarChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, SVGRenderer]);
```

**面试一句话**："移动优先的 PWA 不能拉全量 ECharts——我用 echarts-for-react 的 core 模式 + echarts/core 按需注册，只加载用到的两种图表类型和 SVG 渲染器，省了数百 KB。"

## 二、ChartCard 组件设计（数据注入模式）

```tsx
<ChartCard
  title="打卡热力图（近 8 周）"
  loader={loadHeatmap}        // 模块级常量：稳定引用
  buildOption={heatmapOption} // 纯函数：数据 → ECharts option
  height={160}
/>
```

**关键设计**：
- `loader` 是 `() => Promise<unknown>`——ChartCard 不知道也不关心数据形状；
- `buildOption` 是 `(data) => Record<string, unknown>`——数据到图表配置的映射由调用方定义；
- **loader 必须是稳定引用**（模块级常量或固定依赖的 useCallback），否则每次父渲染都重发请求——这是第九轮审查的 P1-2。

## 三、第九轮审查的三个 P1（全部已修）

### P1-1：热力图日历网格错位

**根因**（两条路径）：
1. 首日是周日：`getDay()` 返回 0，循环 `for (j=1; j<0; j++)` 零次 → 周日落第 0 列（表头"一"）；
2. 后端只返回有任务的天（GROUP BY date）→ 没有任务的日子不在数组里 → 前端按"连续数组每 7 个一行"分组，中间缺一天其后全部左移。

**修法**：按每个日期自身星期算列号（`jsDay===0 ? 6 : jsDay-1`）+ 遍历日期范围补洞（缺失日 rate=-1）。

**教训**：日历网格不能假设数据连续——必须按日期本身的星期分列。

### P1-2：内联箭头函数 loader 导致重复请求

```tsx
// 错误写法：每次渲染都创建新引用
<ChartCard loader={() => api.listStatsHeatmap(8)} ... />
// useLoad 内部 useCallback(loader, [loader]) → 依赖不稳定 → effect 反复触发

// 正确写法：模块级常量
const loadHeatmap = () => api.listStatsHeatmap(8);
<ChartCard loader={loadHeatmap} ... />
```

**后果**：首屏实际 8 次 API 请求（4 图表 × 2 轮），每次通知已读再 +4 次，随交互持续放大。

### P1-3：推送测试按钮假阳性

**问题**：后端 test 接口读 DB 已存配置；用户粘贴新端点后直接点"发测试消息"测试的是旧端点——新端点配错也显示成功。

**修法**：按钮改为"保存并发测试"——先 savePushSettings（写当前表单值到 DB）再 testPush（用 DB 值发测试），加 disabled={sending}。

## 四、SVG renderer 的两个坑

1. **`borderColor: "var(--gc-bg)"` 不生效**（P2-5）：zrender SVG 渲染器把颜色字符串原样写进 SVG 展示属性（`stroke="var(--gc-bg)"`），浏览器不解析展示属性中的 `var()`。改用具体色值 `#FDFCF8`。
2. **图表配色不跟随暗色模式**（P2-6，已知限制）：`#5C8A6E` 等硬编码只对应浅色令牌。修法是用 `getComputedStyle` 读 CSS 变量 + 监听 `prefers-color-scheme` 重建 option——列为 P3 打磨项。

## 五、面试追问预案（4 连）

1. **为什么选 ECharts 不用 Chart.js / D3？** ECharts 对中文生态和移动端优化最好，SVG renderer 对小数据量足够轻；Chart.js 的热力图支持弱，D3 学习成本不匹配"快速交付"的项目节奏；
2. **图表数据在哪加工？** 后端只给结构化数据（JSON），前端 buildOption 纯函数映射——数据与表现分离，改图表类型只改 buildOption 不动后端；
3. **怎么测试图表？** ChartCard 的数据加载和 option 构建是分离的——buildOption 是纯函数可以直接单元测试（输入 JSON → 断言 option 结构），不需要渲染 ECharts 实例；
4. **首屏四个图表并发加载会慢吗？** 模块级常量 loader 保证只发一次；四个请求并发（Promise.all 行为）总耗时 ≈ 最慢的那个；数据量小（几 KB/接口）不是瓶颈。
