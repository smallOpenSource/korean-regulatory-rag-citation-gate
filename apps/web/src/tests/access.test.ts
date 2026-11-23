import { describe, expect, it } from "vitest";

import { canAccessRoute, routeRoles } from "../lib/access";

describe("route RBAC", () => {
  it("keeps audit read-only route limited to ADMIN and AUDIT_VIEWER", () => {
    expect(routeRoles("audit")).toEqual(["ADMIN", "AUDIT_VIEWER"]);
    expect(canAccessRoute("ADMIN", "audit")).toBe(true);
    expect(canAccessRoute("AUDIT_VIEWER", "audit")).toBe(true);
    expect(canAccessRoute("PB", "audit")).toBe(false);
  });

  it("limits consultation workspace to PB and WM", () => {
    expect(canAccessRoute("PB", "consultation")).toBe(true);
    expect(canAccessRoute("WM", "consultation")).toBe(true);
    expect(canAccessRoute("BRANCH_MANAGER", "consultation")).toBe(false);
    expect(canAccessRoute("ADMIN", "consultation")).toBe(false);
  });
});
