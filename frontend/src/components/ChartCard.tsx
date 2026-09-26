"use client";

import { useState } from "react";
import ReactEChartsCore from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart, HeatmapChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import { useLoad } from "@/lib/useLoad";

// 按需注册：只用 bar + heatmap，不拉全量 echarts（P2-7：移动端省数百 KB）
echarts.use([
  BarChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  SVGRenderer,
]);

/** 图表卡容器：标题 + ECharts 实例（数据加载由调用方注入 loader）。
 *
 * 注意：loader 必须是稳定引用（模块级常量或 useCallback 固定依赖），
 * 否则每次父渲染都会重发请求（P1-2 的教训）。
 */
export default function ChartCard({
  title,
  loader,
  buildOption,
  height = 200,
}: {
  title: string;
  loader: () => Promise<unknown>;
  buildOption: (data: unknown) => Record<string, unknown>;
  height?: number;
}) {
  const [data, setData] = useState<unknown>(null);
  const [error, setError] = useState("");

  useLoad(async () => {
    try {
      setData(await loader());
      setError(""); // 成功时清除旧错误（P2-4）
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载失败");
    }
  }, [loader]);

  return (
    <div className="gc-card px-4 py-4">
      <h3 className="mb-3 px-1 text-sm font-medium text-gc-muted">{title}</h3>
      {error ? (
        <p className="py-8 text-center text-xs text-gc-muted">{error}</p>
      ) : data === null ? (
        <p className="py-8 text-center text-xs text-gc-muted">加载中…</p>
      ) : (
        <ReactEChartsCore
          echarts={echarts}
          option={buildOption(data)}
          style={{ height }}
          opts={{ renderer: "svg" }}
          notMerge
          lazyUpdate
        />
      )}
    </div>
  );
}
