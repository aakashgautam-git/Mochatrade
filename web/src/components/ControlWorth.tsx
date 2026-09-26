import { useQuery } from "@tanstack/react-query";

import { fetchScenarioAttribution, parseMoney, rupees } from "../lib/api";
import type { AttributionMetrics } from "../lib/types";
import { Badge, Card, CardBody, CardDescription, CardEyebrow, CardHeader, CardTitle, Skeleton } from "./ui";

/**
 * What each control is worth on one scenario, measured on the engine: alone
 * (only it on, against no controls) and last in (the full stack without it,
 * against the full stack). A saving reads as a plain figure; a cost carries
 * the word and the neg colour, never the colour alone.
 */
export function ControlWorth({ slug }: { slug: string }) {
  const q = useQuery({ queryKey: ["attribution", slug], queryFn: () => fetchScenarioAttribution(slug), staleTime: Infinity });

  return (
    <Card>
      <CardHeader actions={q.data ? <Badge mono>{`policy ${q.data.policy_version} · seed ${q.data.seed}`}</Badge> : null}>
        <CardEyebrow>Attribution</CardEyebrow>
        <CardTitle>What each control is worth</CardTitle>
        <CardDescription>
          Alone: only this control on, against no controls. Last in: the full stack without it, against the full stack. Controls overlap, so a
          control can be worth a lot alone and nothing last in, and one that fights another shows as a cost. Loss here is the attributable loss:
          the part that exists only because of how the event was priced and processed.
        </CardDescription>
      </CardHeader>
      <CardBody>
        {q.isPending ? (
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-48 w-full" />
            <p className="text-xs text-text-dim">Measuring 22 runs if this scenario has not been warmed yet.</p>
          </div>
        ) : !q.data ? (
          <p className="text-sm text-text-dim">Could not measure the controls for this scenario.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs font-medium uppercase tracking-[0.08em] text-text-dim">
                  <th scope="col" className="py-2 pr-4 font-medium">Control</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Alone: loss</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Alone: liquidations</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Last in: loss</th>
                  <th scope="col" className="py-2 text-right font-medium">Last in: liquidations</th>
                </tr>
              </thead>
              <tbody>
                {q.data.controls.map((c) => (
                  <tr key={c.control} className="border-b border-line align-top last:border-0">
                    <td className="py-2 pr-4">
                      <p className="text-text">{c.label}</p>
                      <p className="text-xs text-text-dim">{c.kills}</p>
                    </td>
                    {c.not_modelled ? (
                      <td colSpan={4} className="py-2 text-xs text-text-dim">{c.not_modelled}</td>
                    ) : (
                      <>
                        <Money value={c.alone} />
                        <Count value={c.alone} className="pr-4" />
                        <Money value={c.last_in} />
                        <Count value={c.last_in} />
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-text-dim">
              Without controls: {rupees(parseMoney(q.data.none.attributable_loss))} attributable loss, {q.data.none.accounts_liquidated.toLocaleString("en-IN")} liquidated.
              With the full stack: {rupees(parseMoney(q.data.full.attributable_loss))}, {q.data.full.accounts_liquidated.toLocaleString("en-IN")} liquidated.
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function signed(saved: number, text: string): { label: string; tone: string } {
  if (Math.abs(saved) < 0.5) return { label: "—", tone: "text-text-dim" };
  return saved > 0 ? { label: `saves ${text}`, tone: "text-text" } : { label: `costs ${text}`, tone: "text-neg-fg" };
}

function Money({ value }: { value: AttributionMetrics }) {
  const v = parseMoney(value.attributable_loss);
  const s = signed(v, rupees(Math.abs(v)));
  return <td className={`num whitespace-nowrap py-2 pr-3 text-right ${s.tone}`}>{s.label}</td>;
}

function Count({ value, className = "" }: { value: AttributionMetrics; className?: string }) {
  const n = value.accounts_liquidated;
  const s = signed(n, Math.abs(n).toLocaleString("en-IN"));
  return <td className={`num whitespace-nowrap py-2 text-right ${s.tone} ${className}`}>{s.label}</td>;
}
