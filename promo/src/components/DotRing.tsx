import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, F } from "../theme";

/* The 48-dot ring from the `dot_ring` macro (templates/partials/macros.html), animated:
   dots light up clockwise, filled ones are bigger and fade from .55 to 1 opacity. */
type Props = {
  /** 0..1 fill, already animated by the caller */
  frac: number;
  value: React.ReactNode;
  label?: React.ReactNode;
  size?: number;
  valueSize?: number;
};

export const DotRing: React.FC<Props> = ({ frac, value, label, size = 360, valueSize = 84 }) => {
  const frame = useCurrentFrame();
  const filledExact = Math.max(0, Math.min(1, frac)) * 48;
  return (
    <div style={{ position: "relative", width: size, height: size, flex: "none" }}>
      <svg viewBox="0 0 180 180" width={size} height={size} style={{ display: "block", overflow: "visible" }}>
        {Array.from({ length: 48 }, (_, k) => {
          const ang = (k / 48) * Math.PI * 2 - Math.PI / 2;
          const on = interpolate(filledExact - k, [0, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          // the leading dot "breathes" a little bigger as it arrives
          const lead = on > 0 && on < 1 ? Math.sin(on * Math.PI) * 1.6 : 0;
          const r = 2.4 + (4.2 - 2.4) * on + lead;
          const shimmer = on >= 1 ? 0.06 * Math.sin(frame / 9 - k / 3) : 0;
          return (
            <circle
              key={k}
              cx={90 + 76 * Math.cos(ang)}
              cy={90 + 76 * Math.sin(ang)}
              r={r}
              fill={on > 0 ? "#FFFFFF" : "rgba(255,255,255,.28)"}
              opacity={on > 0 ? Math.min(1, (0.55 + 0.45 * (k / 48)) * (0.4 + 0.6 * on) + shimmer) : 1}
            />
          );
        })}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "#fff", textAlign: "center" }}>
        <span style={{ font: `800 ${valueSize}px/1 ${F.display}`, letterSpacing: "-.03em", fontVariantNumeric: "tabular-nums" }}>{value}</span>
        {label ? <span style={{ marginTop: 12, fontFamily: F.body, fontSize: valueSize * 0.26, lineHeight: 1.35, fontWeight: 600, color: C.heroMuted }}>{label}</span> : null}
      </div>
    </div>
  );
};
