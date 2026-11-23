/**
 * Wave-Audit-Defect-Fix D-S3 — StatusBadge unmapped statusCode no longer
 * lands on the silent blue fallback. Unmapped codes render in red with a
 * `schema_drift (CODE)` label so reviewers see the drift instead of letting
 * it pass through as a harmless-looking blue chip.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../components/Badges";

describe("D-S3: StatusBadge unmapped code surfaces as red schema_drift", () => {
  it("known FAILED stays red with statusLabel rendering", () => {
    render(<StatusBadge statusCode="FAILED" />);
    const el = screen.getByText(/실패/);
    expect(el).toBeInTheDocument();
    expect(el.className).toMatch(/red/);
  });

  it("known APPROVED stays green", () => {
    render(<StatusBadge statusCode="APPROVED" />);
    const el = screen.getByText(/승인/);
    expect(el.className).toMatch(/emerald|green/);
  });

  it("unknown ZZZ_UNMAPPED renders red + schema_drift label including the raw code", () => {
    render(<StatusBadge statusCode="ZZZ_UNMAPPED" />);
    const el = screen.getByText(/schema_drift/);
    expect(el).toBeInTheDocument();
    expect(el.textContent).toContain("ZZZ_UNMAPPED");
    expect(el.className).toMatch(/red/);
  });

  it("did not regress the BLOCKED red detection", () => {
    const { container } = render(<StatusBadge statusCode="POLICY_BLOCKED" />);
    const span = container.querySelector("span");
    expect(span).not.toBeNull();
    expect(span!.className).toMatch(/red/);
  });
});
