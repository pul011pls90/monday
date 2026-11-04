import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, SIZE } from "../theme";
import { PixelText, pixelWidth } from "../components/PixelText";
import { Halftone } from "../components/Halftone";
import { Caption } from "../components/Brand";

/* 0:00–0:04 · Hook. The Home hero line "21 понедельник до экзамена. Этот — твой." as LED pixels. */
export const SceneCountdown: React.FC<{ mondays: number; name: string }> = ({ mondays, name }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const bloom = interpolate(frame, [0, 40], [0, 1], { extrapolateRight: "clamp" });
  const push = interpolate(frame, [0, 240], [1, 1.08]);
  const cell = 34;
  const num = String(mondays);
  const w = pixelWidth(num, cell);
  const eyebrow = spring({ frame: frame - 6, fps, config: { damping: 200 } });

  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ opacity: bloom, background: `radial-gradient(90% 90% at 70% 15%, ${C.mhHi} 0%, ${C.mhMid} 45%, ${C.midnight} 100%)` }} />
      <AbsoluteFill style={{ opacity: bloom * 0.9 }}>
        <Halftone width={SIZE} height={SIZE} step={24} opacity={0.18} rippleAt={18} rx={0.5} ry={0.42} />
      </AbsoluteFill>
      <AbsoluteFill style={{ transform: `scale(${push})`, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 34 }}>
        <div style={{
          fontFamily: F.body, fontSize: 24, fontWeight: 700, letterSpacing: ".14em", textTransform: "uppercase",
          color: C.heroMuted, opacity: eyebrow, transform: `translateY(${(1 - eyebrow) * 16}px)`,
        }}>
          Привет, {name}
        </div>
        <div style={{ width: w, height: cell * 7 }}>
          <PixelText text={num} cell={cell} revealAt={14} revealSpan={40} seed="s1" glow unlit="rgba(255,255,255,.06)" />
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, marginTop: 6 }}>
          <Caption text="понедельник до экзамена." at={62} size={50} />
          <Caption text="Этот — твой." at={104} size={62} color={C.cornflower} stagger={6} />
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
