import { useQuery } from "@tanstack/react-query";

import { useApp } from "../app/store";
import { listIncidents } from "../lib/api";
import type { Incident } from "../lib/types";
import { Select } from "./ui";

/** The incident a page is looking at: the one open in the war room, else the
 * most recent. Changing it here changes it everywhere, including the top bar. */
export function useIncidentSelection(): { code: string | null; incidents: Incident[]; loading: boolean; setCode: (code: string) => void } {
  const storeCode = useApp((s) => s.incidentCode);
  const setIncidentCode = useApp((s) => s.setIncidentCode);
  const incidents = useQuery({ queryKey: ["incidents"], queryFn: listIncidents });
  const list = incidents.data ?? [];
  const code = storeCode && list.some((i) => i.code === storeCode) ? storeCode : list[0]?.code ?? storeCode ?? null;
  return { code, incidents: list, loading: incidents.isLoading, setCode: setIncidentCode };
}

export function IncidentSelect({ code, incidents, onChange }: { code: string; incidents: Incident[]; onChange: (code: string) => void }) {
  return (
    <Select
      label="Incident"
      mono
      value={code}
      onChange={onChange}
      options={incidents.map((i) => ({
        value: i.code,
        label: `${i.code} · ${i.scenario_slug ?? "no run"} · ${i.status.toLowerCase()}`,
      }))}
      className="min-w-[360px]"
    />
  );
}
