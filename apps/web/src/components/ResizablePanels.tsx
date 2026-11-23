/**
 * ResizablePanels — lightweight 3-pane drag-resize layout.
 *
 * Implements the resizable 3-pane workspace required by REG-03 T241.
 * Uses mouse drag on divider handles; keyboard arrow keys also supported
 * for accessibility.  No external dependency — Tailwind + React only.
 *
 * flexBasis inline styles are the minimum necessary for dynamic sizing;
 * static visual styles remain in Tailwind classes.
 */

import { useCallback, useRef, useState } from "react";
import type { ReactNode } from "react";

// ─── Constants ────────────────────────────────────────────────────────────────

/** Minimum pane size as a % of the container width. */
const MIN_PCT = 15;
/** Keyboard nudge per arrow keypress (%). */
const KEY_STEP = 2;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

// ─── DividerHandle ───────────────────────────────────────────────────────────

interface DividerProps {
  onMouseDown: (e: React.MouseEvent) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  label: string;
}

function DividerHandle({ onMouseDown, onKeyDown, label }: DividerProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      className="group relative z-10 flex w-3 shrink-0 cursor-col-resize select-none items-center justify-center focus:outline-none"
      onMouseDown={onMouseDown}
      onKeyDown={onKeyDown}
    >
      {/* Visual track */}
      <div className="h-16 w-0.5 rounded-full bg-slate-200 transition-colors duration-150 group-hover:bg-blue-400 group-focus:bg-blue-500 group-active:bg-blue-600" />
      {/* Grab dots */}
      <div className="absolute flex flex-col gap-0.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-1 w-1 rounded-full bg-slate-300 group-hover:bg-blue-400" />
        ))}
      </div>
    </div>
  );
}

// ─── ThreePaneLayout ─────────────────────────────────────────────────────────

interface ThreePaneLayoutProps {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  /** Initial pane widths as percentages [left, center, right]. Must sum to 100. */
  defaultWidths?: [number, number, number];
}

type DragState = {
  handle: 0 | 1;
  startX: number;
  startWidths: [number, number, number];
};

export function ThreePaneLayout({
  left,
  center,
  right,
  defaultWidths = [25, 47, 28],
}: ThreePaneLayoutProps) {
  const [widths, setWidths] = useState<[number, number, number]>(defaultWidths);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  // ── Mouse drag ─────────────────────────────────────────────────────────────

  const applyDelta = useCallback(
    (handle: 0 | 1, dx: number, base: [number, number, number]) => {
      const [w0, w1, w2] = base;
      if (handle === 0) {
        // Move left/center boundary
        const newLeft = clamp(w0 + dx, MIN_PCT, 100 - w2 - MIN_PCT);
        return [newLeft, 100 - newLeft - w2, w2] as [number, number, number];
      } else {
        // Move center/right boundary (positive dx → right grows)
        const rightEdge = clamp(w0 + w1 + dx, w0 + MIN_PCT, 100 - MIN_PCT);
        return [w0, rightEdge - w0, 100 - rightEdge] as [number, number, number];
      }
    },
    [],
  );

  const startDrag = useCallback(
    (handle: 0 | 1) => (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = { handle, startX: e.clientX, startWidths: [...widths] as [number, number, number] };

      const onMove = (mv: MouseEvent) => {
        if (!dragRef.current || !containerRef.current) return;
        const containerW = containerRef.current.getBoundingClientRect().width;
        if (containerW === 0) return;
        const dxPct = ((mv.clientX - dragRef.current.startX) / containerW) * 100;
        setWidths(applyDelta(dragRef.current.handle, dxPct, dragRef.current.startWidths));
      };

      const onUp = () => {
        dragRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };

      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [widths, applyDelta],
  );

  // ── Keyboard resize ────────────────────────────────────────────────────────

  const onKeyDown = useCallback(
    (handle: 0 | 1) => (e: React.KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const dx = e.key === "ArrowRight" ? KEY_STEP : -KEY_STEP;
      setWidths((prev) => applyDelta(handle, dx, prev));
    },
    [applyDelta],
  );

  return (
    <div
      ref={containerRef}
      className="flex min-h-0 w-full overflow-hidden"
      data-testid="three-pane-layout"
    >
      {/* Left pane */}
      <div
        // dynamic width — required for resize functionality
        style={{ flexBasis: `${widths[0]}%`, flexShrink: 0, minWidth: 0 }}
        className="overflow-y-auto"
      >
        {left}
      </div>

      <DividerHandle
        onMouseDown={startDrag(0)}
        onKeyDown={onKeyDown(0)}
        label="좌측-중앙 패널 크기 조절 (←→ 키 사용 가능)"
      />

      {/* Center pane */}
      <div
        style={{ flexBasis: `${widths[1]}%`, flexShrink: 0, minWidth: 0 }}
        className="overflow-y-auto"
      >
        {center}
      </div>

      <DividerHandle
        onMouseDown={startDrag(1)}
        onKeyDown={onKeyDown(1)}
        label="중앙-우측 패널 크기 조절 (←→ 키 사용 가능)"
      />

      {/* Right pane */}
      <div
        style={{ flexBasis: `${widths[2]}%`, flexShrink: 0, minWidth: 0 }}
        className="overflow-y-auto"
      >
        {right}
      </div>
    </div>
  );
}
