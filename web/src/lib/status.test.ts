import assert from "node:assert/strict";
import { test } from "node:test";

import { groupUpdates } from "./status.ts";
import type { Channel, PublicStatusUpdate } from "./types";

const u = (sequence: number, channel: Channel, display: string, at: string): PublicStatusUpdate => ({
  incident_code: "INC-1", severity: "SEV1", sequence, channel, channel_display: display,
  headline: `#${sequence}`, body: `${display} copy`, published_at: at, next_update_at: null,
});

test("one update on several channels is shown once, status page copy first", () => {
  const grouped = groupUpdates([
    u(1, "X", "X", "2026-09-26T08:09:00+05:30"),
    u(1, "STATUS_PAGE", "Status page", "2026-09-26T08:09:00+05:30"),
    u(1, "WHATSAPP", "WhatsApp", "2026-09-26T08:09:00+05:30"),
    u(2, "X", "X", "2026-09-26T08:18:00+05:30"),
  ]);
  assert.equal(grouped.length, 2);
  assert.equal(grouped[0]?.update.sequence, 2);
  assert.equal(grouped[1]?.update.body, "Status page copy");
  assert.deepEqual(grouped[1]?.channels, ["Status page", "X", "WhatsApp"]);
});
