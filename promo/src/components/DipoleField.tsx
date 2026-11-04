import React, { useLayoutEffect, useMemo, useRef } from "react";
import { random, useCurrentFrame, useVideoConfig } from "remotion";
import { C } from "../theme";

/* Port of the Tuesday "dipole field" scene from monday/static/js/scenes.js (field()),
   driven by the frame number instead of performance.now() so every render is identical.
   `speed` mirrors the before/live modes (live = 1.5). `pulse` (0..1) adds a ring wave from the centre. */
type Props = { width: number; height: number; speed?: number; intensity?: number; pulseAt?: number | null; time?: number };

const TAU = Math.PI * 2;
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export const DipoleField: React.FC<Props> = ({ width, height, speed = 1.5, intensity = 1, pulseAt = null, time }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const geo = useMemo(() => {
    const lines: [number, number, number][][] = [];
    const Ls = [0.22, 0.36, 0.52, 0.7, 0.9, 1.0];
    const nPhi = 12;
    for (const L of Ls)
      for (let k = 0; k < nPhi; k++) {
        const phi = (k / nPhi) * TAU + L * 2;
        const pts: [number, number, number][] = [];
        for (let i = 1; i < 160; i++) {
          const th = (i / 160) * Math.PI;
          const r = L * Math.sin(th) ** 2;
          pts.push([r * Math.sin(th), r * Math.cos(th), phi]);
        }
        lines.push(pts);
      }
    const rings: number[] = [];
    for (let k = 1; k <= 9; k++) rings.push(Math.pow(k / 9, 1.6) * 0.78);
    const grain = Array.from({ length: 5000 }, (_, i) => [random(`g${i}a`), random(`g${i}b`)]);
    return { lines, rings, grain };
  }, []);

  useLayoutEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const ctx = cv.getContext("2d")!;
    const W = width, H = height;
    ctx.clearRect(0, 0, W, H);
    // `time` (seconds) lets the caller change speed without the scene jumping
    const t = time ?? (frame / fps) * speed;
    const R = Math.min(W, H) * 0.44, cx = W / 2, cy = H / 2;
    const rot = t * 0.25, tilt = -0.32;
    const cr = Math.cos(rot), sr = Math.sin(rot), ct = Math.cos(tilt), st = Math.sin(tilt);
    const proj = (x: number, y: number, z: number): [number, number, number] => {
      const X = x * cr + z * sr, Z = -x * sr + z * cr;
      const Y = y * ct - Z * st, Z2 = y * st + Z * ct;
      const s = 3 / (3 + Z2);
      return [cx + X * R * s, cy - Y * R * s, Z2];
    };
    const pulseAge = pulseAt === null ? 1e9 : ((frame - pulseAt) / fps) * 900;
    const pulse = (x: number, y: number) => {
      const d = Math.hypot(x - cx, y - cy);
      return Math.max(0, 1 - Math.abs(d - pulseAge) / 70) * Math.max(0, 1 - pulseAge / 1100);
    };
    for (const pts of geo.lines) {
      pts.forEach(([rho, y, phi], i) => {
        const [x, yy, z] = proj(rho * Math.cos(phi), y, rho * Math.sin(phi));
        const flow = (Math.sin(i * 0.35 - t * 4 + phi * 3) + 1) / 2;
        const depth = clamp(0.55 - z * 0.5, 0.15, 1);
        const l = pulse(x, yy);
        ctx.globalAlpha = clamp((depth * (0.25 + 0.75 * flow ** 3) + l * 0.6) * intensity, 0, 1);
        ctx.fillStyle = flow > 0.92 ? C.paper : C.mist;
        const s = 1.8 + flow ** 4 * 2.4 + l * 3;
        ctx.fillRect(x - s / 2, yy - s / 2, s, s);
      });
    }
    geo.rings.forEach((rr, k) => {
      const n = Math.round(100 + rr * 320);
      for (let i = 0; i < n; i++) {
        const a = (i / n) * TAU + t * (0.6 - k * 0.04);
        const [x, y, z] = proj(Math.cos(a) * rr, 0, Math.sin(a) * rr);
        ctx.globalAlpha = clamp(0.6 - z * 0.4, 0.2, 0.95) * intensity;
        ctx.fillStyle = C.paper;
        ctx.fillRect(x - 1, y - 1, 2, 2);
      }
    });
    for (let i = -70; i <= 70; i++) {
      const [x, y] = proj(0, (i / 70) * 0.98, 0);
      ctx.globalAlpha = 0.55 * intensity;
      ctx.fillStyle = C.paper;
      ctx.fillRect(x - 0.9, y - 0.9, 1.8, 1.8);
    }
    ctx.globalAlpha = 0.05;
    ctx.fillStyle = C.paper;
    for (const [a, b] of geo.grain) ctx.fillRect(a * W, b * H, 1.4, 1.4);
    ctx.globalAlpha = 1;
  }, [frame, fps, width, height, speed, intensity, pulseAt, time, geo]);

  return <canvas ref={ref} width={width} height={height} style={{ position: "absolute", inset: 0, width, height }} />;
};
