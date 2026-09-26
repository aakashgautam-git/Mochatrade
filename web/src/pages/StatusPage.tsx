import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, CheckCircle2, CircleSlash, Clock } from "lucide-react";
import { useEffect } from "react";

import { Skeleton } from "../components/ui";
import { fetchPublicStatus } from "../lib/api";
import { groupUpdates } from "../lib/status";
import type { ComponentState, PublicIncident, PublicStatusResponse } from "../lib/types";

const TONE: Record<ComponentState, { text: string; panel: string; Icon: typeof CheckCircle2 }> = {
  operational: { text: "text-pos-fg", panel: "border-pos-edge bg-pos-soft text-pos-fg", Icon: CheckCircle2 },
  degraded: { text: "text-warn-fg", panel: "border-warn-edge bg-warn-soft text-warn-fg", Icon: AlertTriangle },
  partial_outage: { text: "text-warn-fg", panel: "border-warn-edge bg-warn-soft text-warn-fg", Icon: CircleSlash },
  major_outage: { text: "text-neg-fg", panel: "border-neg-edge bg-neg-soft text-neg-fg", Icon: AlertOctagon },
};

const PHASE: Record<PublicIncident["state"], string> = {
  investigating: "Investigating",
  identified: "Identified",
  monitoring: "Monitoring",
  resolved: "Resolved",
};

const ist = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "";

/**
 * The public status page. Standalone, light, and written for someone whose
 * money is on the line: what works right now, what does not, what we have
 * said, and when we will say more. It reads only /api/status/, which carries
 * nothing internal by construction.
 */
export function StatusPage() {
  useEffect(() => {
    const root = document.documentElement;
    const before = root.dataset.theme;
    root.dataset.theme = "light";
    document.title = "MochaTrade status";
    return () => {
      if (before) root.dataset.theme = before;
      else delete root.dataset.theme;
    };
  }, []);
  const status = useQuery({ queryKey: ["public-status"], queryFn: fetchPublicStatus, refetchInterval: 15_000 });

  return (
    <div className="min-h-screen bg-bg text-text">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <header className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line pb-6">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex h-9 w-9 items-center justify-center rounded-control border border-line bg-surface font-semibold">M</span>
            <div>
              <p className="text-lg font-semibold tracking-tight">MochaTrade</p>
              <p className="text-sm text-text-dim">System status</p>
            </div>
          </div>
          {status.data ? (
            <p className="num flex items-center gap-1.5 text-xs text-text-dim">
              <Clock className="h-3.5 w-3.5" aria-hidden /> As of {ist(status.data.as_of)} IST · refreshes every 15 s
            </p>
          ) : null}
        </header>
        {status.isLoading ? (
          <div className="mt-8 space-y-4">
            <Skeleton className="h-16" />
            <Skeleton className="h-64" />
          </div>
        ) : status.data ? (
          <Body data={status.data} />
        ) : (
          <p className="mt-8 text-sm text-text-dim">The status service is not answering. Updates are also posted on X, WhatsApp and Telegram.</p>
        )}
        <footer className="mt-12 border-t border-line pt-6 text-sm text-text-dim">
          <p className="font-medium text-text">Trades stand. People get made whole.</p>
          <p className="mt-1 leading-relaxed">
            We never reverse a trade; fills are on-chain. When our systems fail you, we compensate under an Abnormal Price Event policy published before
            anything happened, and we tell you here first.
          </p>
        </footer>
      </div>
    </div>
  );
}

function Body({ data }: { data: PublicStatusResponse }) {
  const overall = TONE[data.overall.state];
  const open = data.incidents.filter((i) => i.state !== "resolved");
  const past = data.incidents.filter((i) => i.state === "resolved");
  return (
    <main className="mt-8 space-y-10">
      <section aria-label="Overall status" className={`flex items-center gap-3 rounded-card border px-5 py-4 ${overall.panel}`}>
        <overall.Icon className="h-6 w-6 shrink-0" aria-hidden />
        <p className="text-lg font-semibold">{data.overall.headline}</p>
      </section>

      <section aria-labelledby="components-title">
        <h2 id="components-title" className="text-sm font-medium uppercase tracking-[0.12em] text-text-dim">What works right now</h2>
        <ul className="mt-3 divide-y divide-line rounded-card border border-line bg-surface">
          {data.components.map((c) => {
            const tone = TONE[c.state];
            return (
              <li key={c.name} className="flex items-start justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <p className="font-medium">{c.name}</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-text-dim">{c.note}</p>
                </div>
                <p className={`flex shrink-0 items-center gap-1.5 text-sm font-medium ${tone.text}`}>
                  <tone.Icon className="h-4 w-4" aria-hidden /> {c.state_label}
                </p>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby="incidents-title">
        <h2 id="incidents-title" className="text-sm font-medium uppercase tracking-[0.12em] text-text-dim">
          {open.length ? "Current incident" : "No open incident"}
        </h2>
        {open.length === 0 ? <p className="mt-3 text-sm text-text-dim">Nothing is under investigation.</p> : null}
        <div className="mt-3 space-y-6">{open.map((i) => <IncidentBlock key={i.code} i={i} />)}</div>
      </section>

      {past.length ? (
        <section aria-labelledby="past-title">
          <h2 id="past-title" className="text-sm font-medium uppercase tracking-[0.12em] text-text-dim">Past incidents</h2>
          <div className="mt-3 space-y-6">{past.map((i) => <IncidentBlock key={i.code} i={i} />)}</div>
        </section>
      ) : null}
    </main>
  );
}

function IncidentBlock({ i }: { i: PublicIncident }) {
  const ordered = groupUpdates(i.updates);
  return (
    <article className="rounded-card border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-base font-semibold">{i.title}</h3>
        <p className="text-sm text-text-dim">
          <span className="font-medium text-text">{PHASE[i.state]}</span> · {i.severity} · since {ist(i.started_at)} IST
          {i.resolved_at ? ` · resolved ${ist(i.resolved_at)} IST` : ""}
        </p>
      </div>
      <ol className="mt-4 space-y-4 border-l border-line pl-4">
        {ordered.map(({ update: u, channels }) => (
          <li key={u.sequence}>
            <p className="num text-xs text-text-dim">{ist(u.published_at)} IST · {channels.join(", ")}</p>
            <p className="mt-0.5 text-sm font-medium">{u.headline}</p>
            <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-text-dim">{u.body}</p>
            {u.next_update_at ? <p className="num mt-1 text-xs text-text-dim">Next update by {ist(u.next_update_at)} IST</p> : null}
          </li>
        ))}
      </ol>
    </article>
  );
}
