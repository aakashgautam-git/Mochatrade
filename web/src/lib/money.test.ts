import assert from "node:assert/strict";
import { test } from "node:test";

import { rupees } from "./money.ts";

test("money reads in crore and lakh, the same as the server's text", () => {
  assert.equal(rupees(15_000_000), "₹1.50 Cr");
  assert.equal(rupees(1_017_000), "₹10.17 L");
  assert.equal(rupees(63_947.4), "₹63,947");
  assert.equal(rupees(1_23_456), "₹1.23 L");
  assert.equal(rupees(99_999), "₹99,999");
});

test("the sign goes before the rupee sign, and nothing rounds to minus zero", () => {
  assert.equal(rupees(-2_50_000), "-₹2.50 L");
  assert.equal(rupees(-12_345), "-₹12,345");
  assert.equal(rupees(-0.2), "₹0");
});
