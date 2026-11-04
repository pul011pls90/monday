import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, GRAD_DEEP, SIZE } from "../theme";
import { DotRing } from "../components/DotRing";
import { Halftone } from "../components/Halftone";
import { LogoTile, Caption } from "../components/Brand";
import { Tex } from "../components/Tex";

/* 0:26–0:30 · Outro / Call to Action.
   1. The 48-dot ring rapidly charges clockwise to 100% (target 190).
   2. Floating formulas swirl out from center (like the welcome spiral).
   3. The Monday LogoTile lands with spring, tagline and CTA button. */

const SPIRAL_ITEMS = [
  { tex: "\\int_0^1 x\\,dx", r: 380, a: 0.2 },
  { tex: "a^2 + b^2 = c^2", r: 440, a: 1.4 },
  { tex: "\\lim_{x\\to 0} \\frac{\\sin x}{x}", r: 390, a: 2.5 },
  { tex: "e^{i\\pi} + 1 = 0", r: 420, a: 3.7 },
  { tex: "\\sqrt{2}", r: 350, a: 4.8 },
  { tex: "D = b^2 - 4ac", r: 450, a: 5.6 },
];

export const SceneOutro: React.FC<{ goalScore?: number; ctaUrl?: string }> = ({
  goalScore = 190,
  ctaUrl = "monday.kg",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // 1. Ring fill animation: frames 0 to 80
  const ringProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 60, mass: 0.8 },
  });
  const currentScore = Math.round(interpolate(ringProgress, [0, 1], [125, goalScore]));

  // Ring exits as the brand reveals: frames 90 to 120
  const ringOut = spring({
    frame: frame - 86,
    fps,
    config: { damping: 16, stiffness: 120 },
  });

  // 2. Logo & Brand entrance: frames 94 onwards
  const brandIn = spring({
    frame: frame - 94,
    fps,
    config: { damping: 12, stiffness: 140 },
  });

  // 3. CTA button entrance: frames 124 onwards
  const ctaIn = spring({
    frame: frame - 124,
    fps,
    config: { damping: 13, stiffness: 150 },
  });

  return (
    <AbsoluteFill style={{ background: GRAD_DEEP, overflow: "hidden" }}>
      <Halftone width={SIZE} height={SIZE} step={24} opacity={0.16} rippleAt={94} rx={0.5} ry={0.5} />

      {/* Floating formulas swirling in background */}
      {SPIRAL_ITEMS.map((item, i) => {
        const swirlAngle = item.a + (frame / fps) * 0.4;
        const radius = item.r * (0.8 + 0.2 * Math.sin(frame / 20 + i));
        const x = SIZE / 2 + radius * Math.cos(swirlAngle) - 60;
        const y = SIZE / 2 + radius * Math.sin(swirlAngle) - 20;
        const itemOpacity = interpolate(brandIn, [0, 1], [0.35, 0.15]);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              color: C.powder,
              opacity: itemOpacity,
              transform: `scale(${0.9 + 0.1 * Math.sin(frame / 15 + i)}) rotate(${swirlAngle * 10}deg)`,
              pointerEvents: "none",
            }}
          >
            <Tex tex={item.tex} style={{ fontSize: 26 }} />
          </div>
        );
      })}

      {/* Center 1: DotRing Milestone */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${1 - ringOut * 0.4}) translateY(${-ringOut * 600}px)`,
          opacity: 1 - ringOut,
        }}
      >
        <DotRing
          frac={ringProgress}
          value={currentScore}
          label={<>цель достигнута · {goalScore} баллов</>}
          size={420}
          valueSize={96}
        />
        <div style={{ marginTop: 24 }}>
          <Caption text="Твой результат в твоих руках." at={15} size={38} color="#FFFFFF" />
        </div>
      </div>

      {/* Center 2: Brand Logo, Tagline & CTA */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          transform: `scale(${brandIn}) translateY(${(1 - brandIn) * 120}px)`,
          opacity: brandIn,
          gap: 22,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <LogoTile size={86} />
          <span
            style={{
              fontFamily: F.display,
              fontSize: 78,
              fontWeight: 800,
              color: "#FFFFFF",
              letterSpacing: "-0.03em",
            }}
          >
            Monday
          </span>
        </div>

        <p
          style={{
            fontFamily: F.body,
            fontSize: 32,
            fontWeight: 600,
            color: C.heroMuted,
            margin: "0 0 10px 0",
            textAlign: "center",
            maxWidth: 720,
            lineHeight: 1.3,
          }}
        >
          Готовься к математике осмысленно.
          <br />
          Каждый понедельник.
        </p>

        {/* CTA Button */}
        <div
          style={{
            marginTop: 14,
            transform: `scale(${ctaIn})`,
            opacity: ctaIn,
            display: "inline-flex",
            alignItems: "center",
            gap: 16,
            padding: "20px 48px",
            borderRadius: 999,
            background: "#FFFFFF",
            color: C.midnight,
            boxShadow: "0 14px 40px rgba(0, 0, 0, 0.35)",
          }}
        >
          <span style={{ fontFamily: F.body, fontSize: 28, fontWeight: 800, letterSpacing: "-0.01em" }}>
            Начни бесплатно · {ctaUrl}
          </span>
          <span style={{ fontSize: 32, fontWeight: 900 }}>→</span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
