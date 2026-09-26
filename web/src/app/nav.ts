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
  },
  {
    path: "/war-room",
    label: "War Room",
    icon: Radar,
  },
  {
    path: "/forensics",
    label: "Forensics",
    icon: ScanSearch,
  },
  {
    path: "/remediation",
    label: "Remediation",
    icon: HandCoins,
  },
  {
    path: "/comms",
    label: "Comms",
    icon: Megaphone,
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
