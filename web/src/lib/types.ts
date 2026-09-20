/** API response types. Hand-written to match core/views.py exactly. */

export interface ScenarioRow {
  slug: string;
  name: string;
  summary: string;
  layer: string;
  instrument: string;
  ist_label: string;
  expected_class: string;
}

export interface SeriesPoint {
  t: number;
  oracle: number | null;
  mark: number;
  ltp: number;
  liquidations: number;
}

export interface RunSide {
  liquidated: number;
  unnecessary: number;
  adl: number;
  user_loss_inr: number;
  accounts_total: number;
  trough_pct: number;
  series: SeriesPoint[];
}

export interface Comparison {
  scenario: {
    slug: string;
    name: string;
    summary: string;
    instrument: string;
    ist_label: string;
    layer: string;
    liable_layer_note: string;
    seed: number;
  };
  assumed_scale_note: string;
  off: RunSide;
  on: RunSide;
  delta: {
    liquidated_pct: number;
    loss_pct: number;
    unnecessary_pct: number;
    adl_pct: number;
  };
}
