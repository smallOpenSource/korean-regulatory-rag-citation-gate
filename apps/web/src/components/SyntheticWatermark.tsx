/**
 * SyntheticWatermark
 *
 * Renders a repeating diagonal "SYNTHETIC DEMO DATA" watermark across the
 * page background when synthetic: true is detected in any API response.
 * Uses a fixed-position overlay so it doesn't affect layout.
 * aria-hidden to keep it out of the accessibility tree.
 */

interface Props {
  /** When false the watermark is not rendered. */
  visible: boolean;
}

export function SyntheticWatermark({ visible }: Props) {
  if (!visible) return null;

  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-40 overflow-hidden select-none"
      style={{ isolation: "isolate" }}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundImage: `repeating-linear-gradient(
            -45deg,
            transparent,
            transparent 80px,
            rgba(251, 191, 36, 0.06) 80px,
            rgba(251, 191, 36, 0.06) 82px
          )`,
        }}
      />
      {/* SVG pattern overlay with text */}
      <svg
        className="absolute inset-0 h-full w-full"
        xmlns="http://www.w3.org/2000/svg"
        style={{ opacity: 0.07 }}
      >
        <defs>
          <pattern
            id="synthetic-watermark-pattern"
            x="0"
            y="0"
            width="280"
            height="120"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(-40)"
          >
            <text
              x="0"
              y="60"
              fontFamily="system-ui, sans-serif"
              fontSize="18"
              fontWeight="700"
              fill="#92400e"
              letterSpacing="3"
            >
              SYNTHETIC DEMO DATA
            </text>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#synthetic-watermark-pattern)" />
      </svg>
    </div>
  );
}
