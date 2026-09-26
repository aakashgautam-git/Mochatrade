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
  },
  {
    path: "/playbook",
    label: "Playbook",
    icon: BookOpen,
    document: true,
  },
];
