import React from "react";
import { interpolate, random, spring, useCurrentFrame, useVideoConfig } from "remotion";

/* 5×7 dot-matrix font, identical to window.MondayPixel in monday/static/js/app.js. */
const FONT: Record<string, string[]> = {
  0: ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
  1: ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
  2: ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
  3: ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
  4: ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
  5: ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
  6: ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
  7: ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
  8: ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
  9: ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
  "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
  "#": ["01010", "11111", "01010", "01010", "01010", "11111", "01010"],
  "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
  "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
  "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
  ":": ["0", "0", "1", "0", "1", "0", "0"],
  ".": ["00", "00", "00", "00", "00", "11", "11"],
  " ": ["00", "00", "00", "00", "00", "00", "00"],
};

export const pixelWidth = (text: string, cell: number) =>
  Math.max(cell, [...text].filter((ch) => FONT[ch]).reduce((s, ch) => s + (FONT[ch][0].length + 1) * cell, 0) - cell);

type Props = {
  text: string;
  cell: number;
  lit?: string;
  unlit?: string | null;
  /** frame at which the dots start assembling (relative to the current Sequence) */
  revealAt?: number;
  /** how many frames the scattered assembly takes; 0 = appear immediately */
  revealSpan?: number;
  seed?: string;
  glow?: boolean;
  style?: React.CSSProperties;
};

/** Each lit cell drops in on its own spring, so numbers "assemble" like the podium squares do in ranking.js. */
export const PixelText: React.FC<Props> = ({
  text, cell, lit = "rgba(255,255,255,.92)", unlit = "rgba(255,255,255,.07)",
  revealAt = 0, revealSpan = 0, seed = "px", glow = false, style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const gap = Math.max(1, Math.round(cell / 5));
  const chars = [...text].filter((ch) => FONT[ch]);
  const w = pixelWidth(text, cell);
  const h = 7 * cell;
  const rects: React.ReactNode[] = [];
  let x0 = 0;
  chars.forEach((ch, ci) => {
    const g = FONT[ch];
    g.forEach((row, r) =>
      [...row].forEach((b, c) => {
        const on = b === "1";
        if (!on && !unlit) return;
        let k = 1;
        if (on && revealSpan > 0) {
          const delay = revealAt + random(`${seed}-${ci}-${r}-${c}`) * revealSpan;
          k = spring({ frame: frame - delay, fps, config: { damping: 12, stiffness: 180, mass: 0.6 } });
        }
        const size = cell - gap;
        rects.push(
          <rect
            key={`${ci}-${r}-${c}`}
            x={x0 + c * cell + (size * (1 - k)) / 2}
            y={r * cell + (size * (1 - k)) / 2 - (1 - k) * cell * 3}
            width={Math.max(0, size * k)}
            height={Math.max(0, size * k)}
            rx={size * 0.18}
            fill={on ? lit : (unlit as string)}
            opacity={on ? interpolate(k, [0, 0.3, 1], [0, 1, 1]) : 1}
          />,
        );
      }),
    );
    x0 += (g[0].length + 1) * cell;
  });
  return (
    <svg
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ display: "block", overflow: "visible", filter: glow ? `drop-shadow(0 0 ${cell * 0.8}px rgba(143,166,255,.65))` : undefined, ...style }}
    >
      {rects}
    </svg>
  );
};
