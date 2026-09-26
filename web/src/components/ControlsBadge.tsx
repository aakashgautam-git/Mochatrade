import { Badge } from "./ui";

/** Whether an incident ran with MochaTrade's risk controls. Always in words. */
export function ControlsBadge({ on }: { on: boolean | null | undefined }) {
  if (on === null || on === undefined) return null;
  return <Badge tone={on ? "pos" : "neg"}>{on ? "Controls ON" : "Controls OFF"}</Badge>;
}
