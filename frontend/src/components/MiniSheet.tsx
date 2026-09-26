"use client";

import { useEffect, useRef } from "react";

/** 底部小抽屉：卡因/心情/睡眠共用。Esc 关闭、锁定背景滚动、关闭后还焦。 */
export default function MiniSheet({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousFocus.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = originalOverflow;
      previousFocus.current?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center" role="dialog" aria-modal="true" aria-label={title}>
      <button aria-label="关闭" className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="gc-card gc-slide-up relative z-10 w-full max-w-[480px] rounded-b-none px-6 pb-8 pt-5 outline-none"
      >
        <p className="mb-4 text-sm font-medium text-gc-muted">{title}</p>
        {children}
      </div>
    </div>
  );
}
