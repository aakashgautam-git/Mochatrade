import { useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from "react";

/**
 * A minimal history router: eight routes do not justify a dependency, and the
 * brief for this phase was no new packages. Vite serves index.html for any
 * path in dev and preview, so deep links work.
 */

const listeners = new Set<() => void>();

function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener("popstate", callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener("popstate", callback);
  };
}

export function normalise(path: string): string {
  return path.length > 1 ? path.replace(/\/+$/, "") : path;
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => normalise(window.location.pathname));
}

export function navigate(to: string) {
  if (normalise(to) === normalise(window.location.pathname)) return;
  window.history.pushState(null, "", to);
  listeners.forEach((l) => l());
  window.scrollTo({ top: 0 });
  // Move focus to the page, so keyboard and screen-reader users land on the
  // new content rather than staying on the link they pressed.
  requestAnimationFrame(() => document.getElementById("main")?.focus({ preventScroll: true }));
}

interface LinkProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  to: string;
}

export function Link({ to, onClick, ...rest }: LinkProps) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    // Let the browser handle new-tab and download gestures itself.
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    navigate(to);
  };
  return <a href={to} onClick={handle} {...rest} />;
}
