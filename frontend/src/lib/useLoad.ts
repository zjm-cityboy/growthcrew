"use client";

import { useCallback, useEffect } from "react";

/**
 * 首屏数据加载 Hook：把"effect 里触发异步加载→setState"的模式收敛到一处。
 * （react-hooks/set-state-in-effect 对异步加载器过急，集中豁免一次即可。）
 */
export function useLoad(loader: () => Promise<void>, deps: unknown[] = []) {
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/use-memo -- deps 由调用方传入
  const reload = useCallback(loader, deps);
  useEffect(() => {
    void reload();
  }, [reload]);
  return reload;
}
