import { describe, expect, it } from "vitest";

import { WS_SUBPROTOCOL } from "../lib/websocket";

describe("WebSocket client contract (T287/T297)", () => {
  it("uses harness.v1 subprotocol for ticket-based auth", () => {
    expect(WS_SUBPROTOCOL).toBe("harness.v1");
  });
});
