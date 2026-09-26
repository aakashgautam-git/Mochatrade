import assert from "node:assert/strict";
import { test } from "node:test";

import { actionLabel, formatClock, phaseAt, pillFor, PLAYBOOK, playbookStatus, publicUpdates, stepStatus } from "./warroom.ts";
import type { IncidentAction, Tick } from "./types";

const action = (type: string, tick: number): IncidentAction => ({
  id: tick, tick, wall_clock: "", actor: "IC", action_type: type as IncidentAction["action_type"],
  action_type_display: type, params: {}, rationale: "", reversible: true,
});

const tick = (over: Partial<Tick>): Tick => ({
  halted: false, composite_rung: 1, trading_paused: false, liquidations_paused: false, reduce_only: false,
  ...over,
} as Tick);

test("the playbook follows the research table and ends at T+60", () => {
  assert.equal(PLAYBOOK.length, 11);
  assert.equal(PLAYBOOK[0]?.id, "detect");
  assert.equal(PLAYBOOK.at(-1)?.due, 3600);
  for (const s of PLAYBOOK) assert.ok(s.from <= s.due);
});

test("a step is done only when its decision is logged", () => {
  const contain = PLAYBOOK.find((s) => s.id === "contain")!;
  assert.equal(stepStatus(contain, [], 200).state, "due");
  assert.equal(stepStatus(contain, [], 400).state, "overdue");
  assert.equal(stepStatus(contain, [], 60).state, "upcoming");
  const done = stepStatus(contain, [action("PROTECT_SWITCH", 150)], 400);
  assert.equal(done.state, "done");
  assert.equal(done.doneAt, 150);
});

test("counted steps need the nth update, not just any update", () => {
  const actions = [action("PUBLISH_UPDATE", 200), action("PUBLISH_UPDATE", 800)];
  const byId = Object.fromEntries(playbookStatus(actions, 1000).map((s) => [s.step.id, s]));
  assert.equal(byId["first-word"]?.state, "done");
  assert.equal(byId["update-2"]?.state, "done");
  assert.equal(byId["update-2"]?.doneAt, 800);
  assert.notEqual(byId["update-3"]?.state, "done");
});

test("the phase is the last window that has opened", () => {
  assert.equal(phaseAt(0).id, "detect");
  assert.equal(phaseAt(16 * 60).id, "update-3");
  assert.equal(phaseAt(59 * 60).id, "handover");
});

test("the pill takes the most severe state", () => {
  assert.equal(pillFor(null), "NORMAL");
  assert.equal(pillFor(tick({ reduce_only: true })), "REDUCE_ONLY");
  assert.equal(pillFor(tick({ reduce_only: true, trading_paused: true })), "TRADING_PAUSED");
  assert.equal(pillFor(tick({ liquidations_paused: true })), "LIQ_PAUSED");
  assert.equal(pillFor(tick({ trading_paused: true, composite_rung: 4 })), "DEGRADED_ORACLE");
  assert.equal(pillFor(tick({ halted: true, composite_rung: 4 })), "HALTED");
});

test("the clock reads T+MM:SS", () => {
  assert.equal(formatClock(0), "T+00:00");
  assert.equal(formatClock(252), "T+04:12");
  assert.equal(formatClock(3600), "T+60:00");
});

test("a message to a regulator or the venue is not a public update", () => {
  const privateNote = { ...action("PUBLISH_UPDATE", 200), params: { audience: "REGULATOR" } };
  const publicNote = { ...action("PUBLISH_UPDATE", 260), params: { audience: "PUBLIC" } };
  const firstWord = PLAYBOOK.find((s) => s.id === "first-word")!;
  assert.notEqual(stepStatus(firstWord, [privateNote], 280).state, "done");
  assert.equal(stepStatus(firstWord, [privateNote, publicNote], 280).doneAt, 260);
});

test("one update on several channels is one update", () => {
  const sent = (tick: number, sequence: number, channel: string): IncidentAction => ({
    ...action("PUBLISH_UPDATE", tick), id: tick * 10 + channel.length, params: { audience: "PUBLIC", sequence, channel },
  });
  const actions = [sent(300, 1, "STATUS_PAGE"), sent(300, 1, "X"), sent(300, 1, "WHATSAPP"), sent(840, 2, "STATUS_PAGE")];
  assert.equal(publicUpdates(actions).length, 2);
  const byId = Object.fromEntries(playbookStatus(actions, 1000).map((s) => [s.step.id, s]));
  assert.equal(byId["update-2"]?.doneAt, 840);
  assert.notEqual(byId["update-3"]?.state, "done");
});

test("a publish is labelled by what went out, not by the T+5 slot", () => {
  const sent = (params: Record<string, unknown>): IncidentAction => ({ ...action("PUBLISH_UPDATE", 1800), params });
  assert.equal(actionLabel(sent({ audience: "PUBLIC", sequence: 4, channel: "X" })), "Update 4 on X");
  assert.equal(actionLabel(sent({ audience: "REGULATOR", sequence: 3, channel: "EMAIL" })), "Regulators by email");
  assert.equal(actionLabel(action("CLASSIFY", 800)), "CLASSIFY");
});
