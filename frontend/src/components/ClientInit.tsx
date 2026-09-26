"use client";

import { registerOfflineQueueSync } from "@/lib/offlineQueue";
import { useEffect } from "react";

/** 客户端初始化：注册 Service Worker + 离线队列监听（在根布局挂载一次）。 */
export default function ClientInit() {
  useEffect(() => {
    registerOfflineQueueSync();
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* SW 注册失败不影响功能 */
      });
    }
  }, []);
  return null;
}
