import {
  BookOpen,
  FileText,
  FlaskConical,
  HandCoins,
  LayoutDashboard,
  Megaphone,
  Radar,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";

export interface NavSection {
  path: string;
  label: string;
  icon: LucideIcon;
  /** Documents may be read in the light palette. Everything else is the war room. */
  document?: boolean;
  /** What lands here, and when. Shown on the placeholder until it does. */
  pending?: { phase: number | null; summary: string };
}

export const NAV: NavSection[] = [
  { path: "/", label: "Overview", icon: LayoutDashboard },
  {
    path: "/simulator",
    label: "Simulator",
    icon: FlaskConical,
    pending: { phase: 6, summary: "Run any scenario tick by tick with controls off and on, and watch the cascade form in the book, the mark and the liquidation queue." },
  },
  {
    path: "/war-room",
    label: "War Room",
    icon: Radar,
    pending: { phase: 7, summary: "The 60-minute playbook as a live drill. Declare, throw the Protect Switch, and every decision changes the run and lands in an append-only log." },
  },
  {
    path: "/forensics",
    label: "Forensics",
    icon: ScanSearch,
    pending: { phase: 8, summary: "The Abnormal Price Event test against the per-source evidence tape: deviation, reversion, counterfactual survival, then a root-cause class from A to G." },
  },
  {
    path: "/remediation",
    label: "Remediation",
    icon: HandCoins,
    pending: { phase: 9, summary: "Counterfactual equity per account, provisional credit inside 60 minutes, and the pro-rata path when a claim set exceeds the published cap." },
  },
  {
    path: "/comms",
    label: "Comms",
    icon: Megaphone,
    pending: { phase: 10, summary: "Status page, X and WhatsApp updates on a committed cadence. What we see, what we turned on, and when the next update lands." },
  },
  {
    path: "/report",
    label: "Report",
    icon: FileText,
    document: true,
    pending: { phase: 11, summary: "The incident report: what happened, who is affected, what we are paying, when it lands, and the date of the full root-cause analysis." },
  },
  {
    path: "/playbook",
    label: "Playbook",
    icon: BookOpen,
    document: true,
    pending: { phase: null, summary: "The published playbook, readable before the event: roles, the clock, the Protect Switch, and the three judgment calls to defend out loud." },
  },
];
