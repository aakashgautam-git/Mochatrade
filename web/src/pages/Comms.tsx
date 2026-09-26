import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, FileText, Megaphone, OctagonX, Send, ShieldCheck, TriangleAlert, Undo2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Link } from "../app/router";
import { IncidentSelect, useIncidentSelection } from "../components/IncidentPicker";
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardEyebrow,
  CardHeader,
  CardTitle,
  EmptyState,
  Select,
  Skeleton,
  TextField,
  Toggle,
  toast,
} from "../components/ui";
import { ApiError, checkComms, createComms, decideComms, fetchComms, fetchTemplates, incidentState, publishComms } from "../lib/api";
import type { Audience, Channel, CommsCheckResponse, CommsTemplate, CommsUpdate, Finding } from "../lib/types";

const AUDIENCES: Array<{ value: Audience; label: string }> = [
  { value: "PUBLIC", label: "Everyone" },
  { value: "AFFECTED", label: "Affected users" },
  { value: "VENUE", label: "The venue" },
  { value: "REGULATOR", label: "Regulators" },
];

const CHANNEL_LABEL: Record<Channel, string> = {
  STATUS_PAGE: "Status page",
  X: "X",
  WHATSAPP: "WhatsApp",
  TELEGRAM: "Telegram",
  EMAIL: "Email",
};

export function Comms() {
  const { code, incidents, loading, setCode } = useIncidentSelection();
  return (
    <div className="mx-auto max-w-[1360px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Comms</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">What we know, what we turned on, when we speak next</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-text-dim">
            What we say creates more liability than the incident. COMMS drafts, the IC approves, COMMS sends. Every word is checked against the rules the
            playbook published: no "market conditions", no "your funds are safe" before solvency is verified, no number before it is computed, no arguing,
            no blame.
          </p>
        </div>
        <div className="flex items-end gap-4">
          <a href="/status" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 pb-2 text-sm font-medium text-accent-fg underline underline-offset-4">
            Public status page <ExternalLink className="h-4 w-4" aria-hidden />
          </a>
          {code ? <IncidentSelect code={code} incidents={incidents} onChange={setCode} /> : null}
        </div>
      </header>
      {loading ? (
        <Skeleton className="h-64" />
      ) : code ? (
        <IncidentComms key={code} code={code} />
      ) : (
        <EmptyState
          icon={<Megaphone />}
          title="No incident to speak about"
          description="Declare one in the War Room. The templates fill from its own record."
          action={<Link to="/war-room" className="text-sm font-medium text-accent-fg underline underline-offset-4">Open the War Room</Link>}
        />
      )}
    </div>
  );
}

function IncidentComms({ code }: { code: string }) {
  const queryClient = useQueryClient();
  const updates = useQuery({ queryKey: ["comms", code], queryFn: () => fetchComms(code) });
  const templates = useQuery({ queryKey: ["templates", code], queryFn: () => fetchTemplates(code) });
  const state = useQuery({ queryKey: ["incident-state-lite", code], queryFn: () => incidentState(code) });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["comms", code] });
    await queryClient.invalidateQueries({ queryKey: ["templates", code] });
  };
  const ic = state.data?.incident.incident_commander || "IC";
  const lead = state.data?.incident.comms_lead || "COMMS";

  return (
    <div className="space-y-6">
      <Composer code={code} templates={templates.data ?? []} author={lead} onSaved={refresh} />
      <Queue code={code} updates={updates.data ?? []} ic={ic} lead={lead} onChanged={refresh} loading={updates.isLoading} />
    </div>
  );
}

function Composer({ code, templates, author, onSaved }: { code: string; templates: CommsTemplate[]; author: string; onSaved: () => Promise<void> }) {
  const [audience, setAudience] = useState<Audience>("PUBLIC");
  const options = templates.filter((t) => t.audience === audience);
  const [templateKey, setTemplateKey] = useState<string>("");
  const template = options.find((t) => t.key === templateKey) ?? options[0];
  const channels: Channel[] = template?.channels ?? (audience === "PUBLIC" ? ["STATUS_PAGE", "X", "WHATSAPP", "TELEGRAM"] : ["EMAIL"]);
  const [channel, setChannel] = useState<Channel>("STATUS_PAGE");
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [solvency, setSolvency] = useState(false);
  const [check, setCheck] = useState<CommsCheckResponse | null>(null);
  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);

  useEffect(() => {
    if (!channels.includes(channel)) setChannel(channels[0] ?? "STATUS_PAGE");
  }, [channels, channel]);

  // Live guardrails: the server is the one rulebook, asked a moment after typing stops.
  useEffect(() => {
    if (!headline.trim() && !body.trim()) {
      setCheck(null);
      return;
    }
    const id = window.setTimeout(() => {
      checkComms(code, { headline, body, channel, audience, template: template?.key ?? "", solvency_verified: solvency })
        .then(setCheck)
        .catch(() => setCheck(null));
    }, 350);
    return () => window.clearTimeout(id);
  }, [code, headline, body, channel, audience, template?.key, solvency]);

  const fill = () => {
    const draft = template?.drafts.find((d) => d.channel === channel) ?? template?.drafts[0];
    if (!draft) return;
    setHeadline(draft.headline);
    setBody(draft.body);
  };

  const save = async (submit: boolean) => {
    setBusy(submit ? "submit" : "draft");
    try {
      await createComms(code, {
        headline, body, channel, audience, template: template?.key ?? "", solvency_verified: solvency,
        drafted_by: author, is_published: false, submit,
      });
      toast(submit ? "Sent to the IC" : "Draft saved", { tone: "pos", description: submit ? "It waits in the approval queue below." : "Nothing leaves the building until the IC approves." });
      setHeadline("");
      setBody("");
      setCheck(null);
      await onSaved();
    } catch (e) {
      toast(submit ? "Not sent" : "Not saved", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const blocks = check?.findings.filter((f) => f.severity === "block") ?? [];
  const warns = check?.findings.filter((f) => f.severity === "warn") ?? [];
  const limit = channel === "X" ? 280 : channel === "TELEGRAM" ? 4096 : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <Card>
        <CardHeader>
          <CardEyebrow>Compose</CardEyebrow>
          <CardTitle>Start from the playbook, then make it yours</CardTitle>
          <CardDescription>Templates fill from this incident's own record: its instrument, its classification, its computed number and the next slot on the playbook clock.</CardDescription>
        </CardHeader>
        <CardBody className="space-y-4">
          <div role="group" aria-label="Audience" className="flex flex-wrap gap-2">
            {AUDIENCES.map((a) => (
              <button
                key={a.value}
                type="button"
                aria-pressed={audience === a.value}
                onClick={() => {
                  setAudience(a.value);
                  setTemplateKey("");
                }}
                className={`rounded-control border px-3 py-1.5 text-sm transition-colors duration-150 ${audience === a.value ? "border-accent-edge bg-accent-soft text-accent-fg" : "border-line text-text-dim hover:bg-surface-2"}`}
              >
                {a.label}
              </button>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] md:items-end">
            <Select
              label="Template"
              value={template?.key ?? ""}
              onChange={setTemplateKey}
              options={options.map((t) => ({ value: t.key, label: `${t.when} · ${t.title}` }))}
            />
            <Select label="Channel" value={channel} onChange={(v) => setChannel(v as Channel)} options={channels.map((c) => ({ value: c, label: CHANNEL_LABEL[c] }))} />
            <Button icon={<FileText />} onClick={fill} disabled={!template}>Fill from template</Button>
          </div>
          <TextField label="Headline" value={headline} onChange={setHeadline} />
          <TextField
            label="Body"
            value={body}
            onChange={setBody}
            multiline
            rows={8}
            hint={limit ? `${body.length} of ${limit} characters on ${CHANNEL_LABEL[channel]}.` : `${body.length} characters.`}
            invalid={limit && body.length > limit ? `Over the ${CHANNEL_LABEL[channel]} limit by ${body.length - limit}.` : undefined}
          />
          <Toggle
            checked={solvency}
            onChange={setSolvency}
            label="OPS has verified solvency"
            description="Only then may an update say balances are safe, and it should say what was reconciled."
            readout
          />
          <div className="flex flex-wrap gap-3">
            <Button icon={<FileText />} loading={busy === "draft"} disabled={!headline.trim() || !body.trim()} onClick={() => void save(false)}>Save draft</Button>
            <Button variant="primary" icon={<Send />} loading={busy === "submit"} disabled={!headline.trim() || !body.trim() || blocks.length > 0 || !check} onClick={() => void save(true)}>
              Send to the IC for approval
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardEyebrow>Guardrails, live</CardEyebrow>
          <CardTitle>{!check ? "Waiting for words" : blocks.length ? `${blocks.length} to fix before it can go` : "Clear to send"}</CardTitle>
          <CardDescription>A block stops approval and publishing. A warning goes to the IC with the draft.</CardDescription>
        </CardHeader>
        <CardBody className="space-y-4">
          {check ? (
            <>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <FactRow label="Classified" value={check.facts.classified ? `class ${check.facts.category}` : "not yet"} />
                <FactRow label="Affected set" value={check.facts.classified ? String(check.facts.affected) : "not computed"} />
                <FactRow label="Claims" value={check.facts.claims_open ? (check.facts.pro_rata ? `open, pro-rata ${(check.facts.ratio * 100).toFixed(1)}%` : "open, in full") : "not opened"} />
                <FactRow label="Next playbook slot" value={`${check.facts.next_update} IST`} />
              </dl>
              {check.findings.length === 0 ? (
                <p className="flex items-center gap-2 rounded-control border border-pos-edge bg-pos-soft px-3 py-2 text-sm text-pos-fg">
                  <CheckCircle2 className="h-4 w-4" aria-hidden /> No findings.
                </p>
              ) : (
                <ul className="space-y-2" aria-label="Guardrail findings">
                  {[...blocks, ...warns].map((f, i) => <FindingRow key={`${f.rule}-${i}`} f={f} />)}
                </ul>
              )}
            </>
          ) : (
            <p className="text-sm text-text-dim">Fill from a template or start typing. The rules run as you write.</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-line px-2 py-1.5">
      <dt className="text-text-dim">{label}</dt>
      <dd className="num text-text">{value}</dd>
    </div>
  );
}

function FindingRow({ f }: { f: Finding }) {
  const block = f.severity === "block";
  return (
    <li className={`rounded-control border px-3 py-2 ${block ? "border-neg-edge bg-neg-soft" : "border-warn-edge bg-warn-soft"}`}>
      <p className={`flex items-center gap-2 text-sm font-medium ${block ? "text-neg-fg" : "text-warn-fg"}`}>
        {block ? <OctagonX className="h-4 w-4" aria-hidden /> : <TriangleAlert className="h-4 w-4" aria-hidden />}
        {block ? "Blocked" : "Warning"}
        {f.match ? <span className="num rounded bg-surface px-1.5 text-xs text-text">“{f.match}”</span> : null}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-text">{f.message}</p>
      <p className="mt-0.5 text-xs text-text-dim">{f.source}</p>
    </li>
  );
}

function Queue({ code, updates, ic, lead, onChanged, loading }: { code: string; updates: CommsUpdate[]; ic: string; lead: string; onChanged: () => Promise<void>; loading: boolean }) {
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const groups = useMemo(() => ({
    pending: updates.filter((u) => u.approval === "PENDING"),
    ready: updates.filter((u) => u.approval === "APPROVED" && !u.is_published),
    drafts: updates.filter((u) => u.approval === "DRAFT" || u.approval === "REJECTED"),
    sent: updates.filter((u) => u.is_published).sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? "")),
  }), [updates]);

  const run = async (id: number, fn: () => Promise<unknown>, ok: string) => {
    setBusy(id);
    try {
      await fn();
      toast(ok, { tone: "pos" });
      await onChanged();
    } catch (e) {
      toast("Refused", { tone: "neg", description: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <Skeleton className="h-48" />;
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardEyebrow>Awaiting the IC · {ic}</CardEyebrow>
          <CardTitle>{groups.pending.length ? `${groups.pending.length} to decide` : "Nothing waiting"}</CardTitle>
          <CardDescription>Approval re-runs the guardrails against the incident as it stands now. Sending back needs a reason.</CardDescription>
        </CardHeader>
        <CardBody className="space-y-3">
          {groups.pending.map((u) => (
            <UpdateCard key={u.id} u={u}>
              <TextField label="Note to COMMS" value={notes[u.id] ?? ""} onChange={(v) => setNotes({ ...notes, [u.id]: v })} placeholder="Required to send it back" />
              <div className="flex gap-2">
                <Button size="sm" variant="primary" icon={<ShieldCheck />} loading={busy === u.id} onClick={() => void run(u.id, () => decideComms(code, u.id, { decision: "APPROVE", approver: ic, note: notes[u.id] ?? "" }), "Approved")}>
                  Approve as {ic}
                </Button>
                <Button size="sm" variant="danger" icon={<Undo2 />} disabled={busy === u.id} onClick={() => void run(u.id, () => decideComms(code, u.id, { decision: "REJECT", approver: ic, note: notes[u.id] ?? "" }), "Sent back")}>
                  Send back
                </Button>
              </div>
            </UpdateCard>
          ))}
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-text-dim">Approved, ready to send · {lead}</p>
          {groups.ready.length === 0 ? <p className="text-sm text-text-dim">Nothing approved and unsent.</p> : null}
          {groups.ready.map((u) => (
            <UpdateCard key={u.id} u={u}>
              <Button size="sm" variant="primary" icon={<Send />} loading={busy === u.id} onClick={() => void run(u.id, () => publishComms(code, u.id, lead), u.audience === "PUBLIC" ? "Published" : "Sent")}>
                {u.audience === "PUBLIC" ? `Publish on ${u.channel_display}` : `Send by ${u.channel_display}`}
              </Button>
            </UpdateCard>
          ))}
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardEyebrow>Record</CardEyebrow>
          <CardTitle>Sent, and drafts</CardTitle>
          <CardDescription>Everything that left the building, newest first, with who approved it and what the guardrails said.</CardDescription>
        </CardHeader>
        <CardBody className="space-y-3">
          {groups.sent.length === 0 && groups.drafts.length === 0 ? <p className="text-sm text-text-dim">Nothing yet.</p> : null}
          {groups.sent.map((u) => <UpdateCard key={u.id} u={u} />)}
          {groups.drafts.map((u) => <UpdateCard key={u.id} u={u} />)}
        </CardBody>
      </Card>
    </div>
  );
}

function UpdateCard({ u, children }: { u: CommsUpdate; children?: React.ReactNode }) {
  const blocks = u.guardrails.filter((f) => f.severity === "block").length;
  const warns = u.guardrails.filter((f) => f.severity === "warn").length;
  const tone = u.is_published ? "pos" : u.approval === "REJECTED" ? "neg" : u.approval === "PENDING" ? "warn" : "neutral";
  return (
    <article className="space-y-2 rounded-control border border-line px-4 py-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge mono tone="neutral">#{u.sequence}</Badge>
        <Badge tone="neutral">{u.audience_display}</Badge>
        <Badge tone="neutral">{u.channel_display}</Badge>
        <Badge tone={tone}>{u.is_published ? "Sent" : u.approval_display}</Badge>
        {blocks ? <Badge tone="neg">{blocks} blocked</Badge> : null}
        {warns ? <Badge tone="warn">{warns} warning{warns > 1 ? "s" : ""}</Badge> : null}
      </div>
      <p className="text-sm font-medium text-text">{u.headline}</p>
      <p className="whitespace-pre-line text-xs leading-relaxed text-text-dim">{u.body}</p>
      <p className="text-xs text-text-dim">
        Drafted by {u.drafted_by || "COMMS"}
        {u.approved_by ? ` · ${u.approval === "REJECTED" ? "sent back" : "approved"} by ${u.approved_by}` : ""}
        {u.approval_note ? ` — “${u.approval_note}”` : ""}
        {u.published_at ? ` · sent ${new Date(u.published_at).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" })} IST` : ""}
      </p>
      {children}
    </article>
  );
}
