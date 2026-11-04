import React, { useLayoutEffect, useRef } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

/* Ordered halftone grid from the login page / home hero (welcome.js, hero.js):
   dots grow towards the bottom-right, a slow diagonal wave runs through them,
   and an optional ring wave expands from (rx, ry) starting at `rippleAt`. */
type Props = {
  width: number;
  height: number;
  step?: number;
  maxR?: number;
  color?: string;
  opacity?: number;
  rippleAt?: number | null;
  rx?: number;
  ry?: number;
};

export const Halftone: React.FC<Props> = ({
  width, height, step = 22, maxR = 4.2, color = "255,255,255", opacity = 0.22, rippleAt = null, rx = 0.5, ry = 0.5,
}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  useLayoutEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d")!;
    ctx.clearRect(0, 0, width, height);
    const t = frame / fps;
    const age = rippleAt === null ? 1e9 : ((frame - rippleAt) / fps) * 1100;
    const ox = rx * width, oy = ry * height;
    for (let y = step / 2; y < height; y += step) {
      for (let x = step / 2; x < width; x += step) {
        const base = 0.25 + 0.75 * ((x / width) * 0.55 + (y / height) * 0.45) ** 1.6;
        const wave = 0.5 + 0.5 * Math.sin((x + y) / 120 - t * 1.6);
        const d = Math.hypot(x - ox, y - oy);
        const ring = Math.max(0, 1 - Math.abs(d - age) / 80) * Math.max(0, 1 - age / 1600);
        const r = maxR * base * (0.55 + 0.45 * wave) + ring * maxR * 1.2;
        if (r < 0.3) continue;
        ctx.fillStyle = `rgba(${color},${Math.min(1, opacity * (0.6 + 0.6 * base) + ring * 0.5)})`;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }, [frame, fps, width, height, step, maxR, color, opacity, rippleAt, rx, ry]);

  return <canvas ref={ref} width={width} height={height} style={{ position: "absolute", inset: 0, width, height }} />;
};
