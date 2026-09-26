import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * The live state of the market as the operator sees it. Driven by the war room
 * from the open incident's engine flags. A simulator replay must never drive
 * it: a replay is not the live market.
 */
export type SystemState =
  | "NORMAL"
  | "REDUCE_ONLY"
  | "TRADING_PAUSED"
  | "LIQ_PAUSED"
  | "HALTED"
  | "DEGRADED_ORACLE";

interface AppState {
  railCollapsed: boolean;
  toggleRail: () => void;

  /** Report and Playbook only: read them in the light palette. */
  documentLight: boolean;
  setDocumentLight: (on: boolean) => void;

  /** Kitchen sink only: preview the document palette without leaving the page. */
  previewDocumentTheme: boolean;
  setPreviewDocumentTheme: (on: boolean) => void;

  systemState: SystemState;
  setSystemState: (s: SystemState) => void;

  instrument: string | null;
  setInstrument: (symbol: string | null) => void;

  incidentCode: string | null;
  setIncidentCode: (code: string | null) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      railCollapsed: false,
      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
      // Report and Playbook are documents: they open in the light palette.
      documentLight: true,
      setDocumentLight: (on) => set({ documentLight: on }),
      previewDocumentTheme: false,
      setPreviewDocumentTheme: (on) => set({ previewDocumentTheme: on }),
      systemState: "NORMAL",
      setSystemState: (systemState) => set({ systemState }),
      instrument: null,
      setInstrument: (instrument) => set({ instrument }),
      incidentCode: null,
      setIncidentCode: (incidentCode) => set({ incidentCode }),
    }),
    {
      name: "mochatrade-ui",
      // Preferences only. Market state must never be restored from a stale tab.
      partialize: (s) => ({ railCollapsed: s.railCollapsed, documentLight: s.documentLight }),
    },
  ),
);
