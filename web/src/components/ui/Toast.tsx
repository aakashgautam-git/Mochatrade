import { CircleCheck, Info, OctagonX, TriangleAlert, X } from "lucide-react";
import { create } from "zustand";

import { cn } from "./cn";
import { FG, type Tone } from "./tone";

type ToastTone = Extract<Tone, "neutral" | "pos" | "neg" | "warn">;

interface ToastItem {
  id: number;
  title: string;
  description?: string | undefined;
  tone: ToastTone;
}

interface ToastStore {
  items: ToastItem[];
  push: (t: Omit<ToastItem, "id">) => void;
  dismiss: (id: number) => void;
}

let seq = 0;

const useToasts = create<ToastStore>((set) => ({
  items: [],
  push: (t) => set((s) => ({ items: [...s.items.slice(-3), { ...t, id: ++seq }] })),
  dismiss: (id) => set((s) => ({ items: s.items.filter((i) => i.id !== id) })),
}));

/**
 * Raise a toast. Errors stay until dismissed; everything else leaves after six
 * seconds, which is long enough to read two lines.
 */
export function toast(title: string, opts: { description?: string; tone?: ToastTone } = {}) {
  const tone = opts.tone ?? "neutral";
  useToasts.getState().push({ title, description: opts.description, tone });
  if (tone !== "neg") {
    const id = seq;
    window.setTimeout(() => useToasts.getState().dismiss(id), 6000);
  }
}

const ICON = { neutral: Info, pos: CircleCheck, warn: TriangleAlert, neg: OctagonX } as const;

export function ToastRegion() {
  const { items, dismiss } = useToasts();
  return (
    <div
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-[22rem] max-w-[calc(100vw-3rem)] flex-col gap-2"
    >
      {items.map((t) => {
        const Icon = ICON[t.tone];
        return (
          <div
            key={t.id}
            role={t.tone === "neg" ? "alert" : "status"}
            className="ui-toast pointer-events-auto flex items-start gap-3 rounded-card border border-line bg-surface-2 p-4"
          >
            <Icon aria-hidden className={cn("mt-0.5 h-4 w-4 shrink-0", FG[t.tone])} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-text">{t.title}</p>
              {t.description ? <p className="mt-1 text-sm leading-relaxed text-text-dim">{t.description}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
              className="rounded-chip p-1 text-text-dim transition-colors duration-fast hover:bg-surface hover:text-text"
            >
              <X aria-hidden className="h-4 w-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
