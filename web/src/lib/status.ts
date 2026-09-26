/**
 * The public status page's view of an incident's updates. Pure, with type-only
 * imports, so Node's test runner can load it without a bundler.
 */
import type { PublicStatusUpdate } from "./types";

export interface GroupedUpdate {
  /** The copy shown: the status page's own, else the first channel sent. */
  update: PublicStatusUpdate;
  /** Every channel this update went out on, status page first. */
  channels: string[];
}

/**
 * One entry per update number, newest first. The same update sent to the
 * status page, X and WhatsApp is one update on three channels; listing it
 * three times reads as three announcements.
 */
export function groupUpdates(updates: readonly PublicStatusUpdate[]): GroupedUpdate[] {
  const bySequence = new Map<number, PublicStatusUpdate[]>();
  for (const u of updates) {
    const list = bySequence.get(u.sequence);
    if (list) list.push(u);
    else bySequence.set(u.sequence, [u]);
  }
  const out: GroupedUpdate[] = [];
  for (const list of bySequence.values()) {
    const ordered = [...list].sort((a, b) =>
      a.channel === "STATUS_PAGE" ? -1 : b.channel === "STATUS_PAGE" ? 1 : (a.published_at ?? "").localeCompare(b.published_at ?? ""),
    );
    out.push({ update: ordered[0] as PublicStatusUpdate, channels: ordered.map((u) => u.channel_display) });
  }
  return out.sort(
    (a, b) => (b.update.published_at ?? "").localeCompare(a.update.published_at ?? "") || b.update.sequence - a.update.sequence,
  );
}
