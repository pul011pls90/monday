import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

/* A finger/cursor that glides between points and taps (press scale + ripple ring).
   path: list of { f: frame, x, y, tap? } keyframes (relative to the Sequence). */
export type CursorKey = { f: number; x: number; y: number; tap?: boolean };

export const Cursor: React.FC<{ path: CursorKey[]; appearAt?: number; hideAt?: number }> = ({ path, appearAt = 0, hideAt = 1e9 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!path.length) return null;

  // position: spring-eased travel between consecutive keys
  let x = path[0].x, y = path[0].y;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1], b = path[i];
    const k = spring({ frame: frame - a.f, fps, durationInFrames: Math.max(8, b.f - a.f), config: { damping: 200 } });
    x = interpolate(k, [0, 1], [x, b.x]);
    y = interpolate(k, [0, 1], [y, b.y]);
  }
  // tap: press down then release, plus a ripple
  let press = 0, ripple = -1;
  for (const key of path)
    if (key.tap) {
      const d = frame - key.f;
      if (d >= -6 && d < 14) press = Math.max(press, interpolate(d, [-6, 0, 10], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
      if (d >= 0 && d < 30) ripple = d / 30;
    }
  const vis = interpolate(frame, [appearAt, appearAt + 10, hideAt, hideAt + 10], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <div style={{ position: "absolute", left: 0, top: 0, transform: `translate(${x}px, ${y}px)`, opacity: vis, pointerEvents: "none", zIndex: 50 }}>
      {ripple >= 0 && (
        <div style={{
          position: "absolute", left: -40, top: -40, width: 80, height: 80, borderRadius: "50%",
          border: "3px solid rgba(255,255,255,.9)", boxShadow: "0 0 0 2px rgba(31,79,224,.35)",
          transform: `scale(${0.3 + ripple * 1.4})`, opacity: 1 - ripple,
        }} />
      )}
      <div style={{
        position: "absolute", left: -22, top: -22, width: 44, height: 44, borderRadius: "50%",
        background: "rgba(255,255,255,.95)", border: "3px solid #153893",
        boxShadow: "0 8px 24px rgba(2,11,41,.35)", transform: `scale(${1 - press * 0.25})`,
      }} />
    </div>
  );
};
