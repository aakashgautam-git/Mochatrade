import { Palette } from "lucide-react";

import type { NavSection } from "../app/nav";
import { Link } from "../app/router";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";

/** A section that is designed but not built yet. Says exactly what lands here
 * and in which phase, rather than rendering a half-built screen. */
export function Placeholder({ section }: { section: NavSection }) {
  const Icon = section.icon;
  const phase = section.pending?.phase;
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8 flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{section.label}</h1>
        <Badge mono>{phase ? `Phase ${phase}` : "Not yet scheduled"}</Badge>
      </div>
      <EmptyState
        icon={<Icon />}
        title={`${section.label} is not built yet`}
        description={section.pending?.summary}
        action={
          <Link
            to="/kitchen-sink"
            className="inline-flex h-9 items-center gap-2 rounded-control border border-line px-4 text-sm text-text transition-colors duration-fast hover:bg-surface-2"
          >
            <Palette aria-hidden className="h-4 w-4" />
            Review the design system
          </Link>
        }
      />
      {section.document ? (
        <p className="mt-6 text-sm text-text-dim">
          This is a document page, so it can be read in either palette. The
          toggle is at the right of the top bar.
        </p>
      ) : null}
    </div>
  );
}
