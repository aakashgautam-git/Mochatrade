import { NAV } from "./app/nav";
import { usePathname } from "./app/router";
import { Shell } from "./app/Shell";
import { useApp } from "./app/store";
import { Comms } from "./pages/Comms";
import { Forensics } from "./pages/Forensics";
import { KitchenSink } from "./pages/KitchenSink";
import { LegacyDemo } from "./pages/LegacyDemo";
import { Placeholder } from "./pages/Placeholder";
import { Remediation } from "./pages/Remediation";
import { Simulator } from "./pages/Simulator";
import { StatusPage } from "./pages/StatusPage";
import { WarRoom } from "./pages/WarRoom";

/**
 * Routes. `/demo` is the screening-round page, standalone and unchanged: the
 * fallback if round 2 comes early. Everything else renders inside the shell.
 */
export function App() {
  const path = usePathname();
  const preview = useApp((s) => s.previewDocumentTheme);

  if (path === "/demo") return <LegacyDemo />;
  if (path === "/status") return <StatusPage />;

  const section = NAV.find((s) => s.path === path);

  if (path === "/simulator") {
    return (
      <Shell current={section} title="Simulator" isDocument={false}>
        <Simulator />
      </Shell>
    );
  }

  if (path === "/kitchen-sink") {
    return (
      <Shell current={undefined} title="Design system" isDocument={false} previewTheme={preview}>
        <KitchenSink />
      </Shell>
    );
  }

  if (path === "/") {
    return (
      <Shell current={section} title="Overview" isDocument={false}>
        <LegacyDemo embedded />
      </Shell>
    );
  }

  if (path === "/war-room") {
    return (
      <Shell current={section} title="War Room" isDocument={false}>
        <WarRoom />
      </Shell>
    );
  }

  if (path === "/forensics") {
    return (
      <Shell current={section} title="Forensics" isDocument={false}>
        <Forensics />
      </Shell>
    );
  }

  if (path === "/remediation") {
    return (
      <Shell current={section} title="Remediation" isDocument={false}>
        <Remediation />
      </Shell>
    );
  }

  if (path === "/comms") {
    return (
      <Shell current={section} title="Comms" isDocument={false}>
        <Comms />
      </Shell>
    );
  }

  if (section) {
    return (
      <Shell current={section} title={section.label} isDocument={section.document === true}>
        <Placeholder section={section} />
      </Shell>
    );
  }

  return (
    <Shell current={undefined} title="Not found" isDocument={false}>
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Nothing at {path}</h1>
        <p className="mt-2 text-sm text-text-dim">Use the navigation to the left.</p>
      </div>
    </Shell>
  );
}
