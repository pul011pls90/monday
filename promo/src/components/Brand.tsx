import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { F } from "../theme";

/* The Monday "M" tile, path taken from monday/static/img/favicon.svg. */
export const LogoTile: React.FC<{ size: number }> = ({ size }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" style={{ display: "block" }}>
    <defs>
      <linearGradient id="mg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#2B60E5" />
        <stop offset=".7" stopColor="#153893" />
        <stop offset="1" stopColor="#020B29" />
      </linearGradient>
    </defs>
    <rect width="64" height="64" rx="14" fill="url(#mg)" />
    <path d="M14 46V18h8l10 16 10-16h8v28h-8V31l-10 15-10-15v15z" fill="#fff" />
  </svg>
);

/* Word-by-word caption: each word rises on its own spring. */
export const Caption: React.FC<{
  text: string;
  at?: number;
  out?: number | null;
  size?: number;
  weight?: number;
  font?: string;
  color?: string;
  stagger?: number;
  align?: "left" | "center";
  style?: React.CSSProperties;
}> = ({ text, at = 0, out = null, size = 44, weight = 800, font = F.display, color = "#fff", stagger = 4, align = "center", style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");
  const fadeOut = out === null ? 1 : interpolate(frame, [out, out + 12], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: align === "center" ? "center" : "flex-start", gap: `0 ${size * 0.28}px`, opacity: fadeOut, ...style }}>
      {words.map((w, i) => {
        const k = spring({ frame: frame - at - i * stagger, fps, config: { damping: 14, stiffness: 160 } });
        return (
          <span key={i} style={{ display: "inline-block", overflow: "hidden", paddingBottom: size * 0.12 }}>
            <span style={{
              display: "inline-block", font: `${weight} ${size}px/1.12 ${font}`, letterSpacing: "-.02em", color,
              transform: `translateY(${(1 - k) * size * 1.1}px)`, opacity: interpolate(k, [0, 0.4], [0, 1], { extrapolateRight: "clamp" }),
            }}>{w}</span>
          </span>
        );
      })}
    </div>
  );
};
