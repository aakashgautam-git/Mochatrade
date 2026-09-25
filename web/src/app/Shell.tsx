import { Moon, PanelLeftClose, PanelLeftOpen, Palette, Sun } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { Badge } from "../components/ui/Badge";
import { cn } from "../components/ui/cn";
import { ToastRegion } from "../components/ui/Toast";
import { useNow } from "../hooks/useNow";
import { NAV, type NavSection } from "./nav";
import { Link, usePathname } from "./router";
import { useApp } from "./store";
import { LOOK, SystemStatePill } from "./SystemStatePill";

const IST_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const IST_DAY = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Kolkata",
  weekday: "short",
  day: "2-digit",
  month: "short",
});

function IstClock() {
  const now = useNow(1000);
  const date = new Date(now);
  return (
    <time dateTime={date.toISOString()} className="flex items-baseline gap-2" aria-label="India Standard Time">
      <span className="text-xs text-text-dim">{IST_DAY.format(date)}</span>
      <span className="num text-sm text-text">{IST_TIME.format(date)}</span>
      <span className="text-xs text-text-dim">IST</span>
    </time>
  );
}

/** A 2px band across the top of the viewport in the state colour. Unmissable
 * from across a room; absent entirely when the market is normal. */
function StateStrip() {
  const state = useApp((s) => s.systemState);
  const strip = LOOK[state].strip;
  if (!strip) return null;
  return <div aria-hidden className={cn("fixed inset-x-0 top-0 z-40 h-0.5", strip)} />;
}

function Rail({ current }: { current: NavSection | undefined }) {
  const collapsed = useApp((s) => s.railCollapsed);
  const toggle = useApp((s) => s.toggleRail);
  const pathname = usePathname();

  return (
    <aside
      id="rail"
      aria-label="Primary"
      className={cn(
        "sticky top-0 flex h-screen shrink-0 flex-col border-r border-line bg-bg",
        "transition-[width] duration-base ease-out",
        collapsed ? "w-16" : "w-[220px]",
      )}
    >
      <div className="flex h-14 items-center gap-3 border-b border-line px-4">
        <span
          aria-hidden
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-control border border-accent-edge bg-accent-soft text-sm font-semibold text-accent-fg"
        >
          M
        </span>
        {!collapsed ? (
          <div className="min-w-0 leading-tight">
            <p className="truncate text-sm font-semibold tracking-tight">MochaTrade</p>
            <p className="truncate text-xs text-text-dim">Crisis Command</p>
          </div>
        ) : (
          <span className="sr-only">MochaTrade Crisis Command</span>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-4">
        <ul className="space-y-1">
          {NAV.map((item) => {
            const active = current?.path === item.path;
            const Icon = item.icon;
            return (
              <li key={item.path}>
                <Link
                  to={item.path}
                  aria-current={active ? "page" : undefined}
                  aria-label={collapsed ? item.label : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "relative flex h-9 items-center gap-3 rounded-control px-3 text-sm",
                    "transition-colors duration-fast ease-out",
                    active ? "bg-surface-2 text-text" : "text-text-dim hover:bg-surface hover:text-text",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active ? <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" /> : null}
                  <Icon aria-hidden className="h-4 w-4 shrink-0" />
                  {!collapsed ? <span className="truncate">{item.label}</span> : null}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="space-y-1 border-t border-line px-2 py-3">
        <Link
          to="/kitchen-sink"
          aria-current={pathname === "/kitchen-sink" ? "page" : undefined}
          aria-label={collapsed ? "Design system" : undefined}
          title={collapsed ? "Design system" : undefined}
          className={cn(
            "relative flex h-9 items-center gap-3 rounded-control px-3 text-sm transition-colors duration-fast",
            pathname === "/kitchen-sink" ? "bg-surface-2 text-text" : "text-text-dim hover:bg-surface hover:text-text",
            collapsed && "justify-center px-0",
          )}
        >
          {pathname === "/kitchen-sink" ? <span aria-hidden className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-accent" /> : null}
          <Palette aria-hidden className="h-4 w-4 shrink-0" />
          {!collapsed ? <span>Design system</span> : null}
        </Link>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-controls="rail"
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          className={cn(
            "flex h-9 w-full items-center gap-3 rounded-control px-3 text-sm text-text-dim transition-colors duration-fast hover:bg-surface hover:text-text",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? <PanelLeftOpen aria-hidden className="h-4 w-4" /> : <PanelLeftClose aria-hidden className="h-4 w-4" />}
          {!collapsed ? <span>Collapse</span> : null}
        </button>
      </div>
    </aside>
  );
}

function TopBar({ title, document }: { title: string; document: boolean }) {
  const state = useApp((s) => s.systemState);
  const instrument = useApp((s) => s.instrument);
  const incident = useApp((s) => s.incidentCode);
  const light = useApp((s) => s.documentLight);
  const setLight = useApp((s) => s.setDocumentLight);

  return (
    <header className="sticky top-0 z-30 grid h-14 grid-cols-[1fr_auto_1fr] items-center gap-4 border-b border-line bg-bg px-8">
      <div className="flex min-w-0 items-center gap-3">
        <p className="truncate text-sm font-medium">{title}</p>
        {instrument ? <Badge mono>{instrument}</Badge> : null}
      </div>

      <div role="status" aria-live="polite" className="flex items-center gap-3">
        <span className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">System</span>
        <SystemStatePill state={state} />
        <span className="sr-only">{LOOK[state].meaning}</span>
      </div>

      <div className="flex items-center justify-end gap-4">
        {incident ? <Badge tone="neg" mono>{incident}</Badge> : null}
        <IstClock />
        {document ? (
          <button
            type="button"
            onClick={() => setLight(!light)}
            aria-pressed={light}
            className="flex h-8 items-center gap-2 rounded-control border border-line px-3 text-xs text-text-dim transition-colors duration-fast hover:bg-surface-2 hover:text-text"
          >
            {light ? <Moon aria-hidden className="h-3.5 w-3.5" /> : <Sun aria-hidden className="h-3.5 w-3.5" />}
            {light ? "Dark" : "Light"}
          </button>
        ) : null}
      </div>
    </header>
  );
}

/**
 * The palette is dark everywhere except Report and Playbook, which may be read
 * light. The theme is set on the root element because tokens.css scopes the
 * light palette to :root[data-theme="light"].
 */
function useDocumentTheme(isDocument: boolean, preview: boolean) {
  const light = useApp((s) => s.documentLight);
  useEffect(() => {
    const root = document.documentElement;
    if ((isDocument && light) || preview) root.dataset.theme = "light";
    else delete root.dataset.theme;
  }, [isDocument, light, preview]);
}

export function Shell({
  current,
  title,
  isDocument,
  previewTheme = false,
  children,
}: {
  current: NavSection | undefined;
  title: string;
  isDocument: boolean;
  previewTheme?: boolean;
  children: ReactNode;
}) {
  useDocumentTheme(isDocument, previewTheme);
  return (
    <div className="min-h-screen bg-bg text-text">
      <a href="#main" className="skip-link">Skip to content</a>
      <StateStrip />
      <div className="flex">
        <Rail current={current} />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar title={title} document={isDocument} />
          <main id="main" tabIndex={-1} className="flex-1 px-8 py-8 outline-none">
            {children}
          </main>
        </div>
      </div>
      <ToastRegion />
    </div>
  );
}
