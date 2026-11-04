import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, F, MH_BG, SIZE } from "../theme";
import { Halftone } from "../components/Halftone";
import { Caption } from "../components/Brand";

/* 0:04–0:08 · The Home "Monday strip": one dot per Monday until the exam.
   Past dots carry the Monday-test score (bigger + brighter = better), "now" pulses (strip-pulse),
   then we iris into the "now" dot, which opens onto the Monday test. */
const PAST = [40, 50, 50, 60, 70, 80]; // staged scores, %
const TOTAL = 24;
const DOT = 22, GAP = 15;

export const SceneStrip: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rowW = TOTAL * DOT + (TOTAL - 1) * GAP;
  const x0 = (SIZE - rowW) / 2 - 60; // leave room for the "экзамен" label on the right
  const y = 560;
  const nowIdx = PAST.length;
  const nowX = x0 + nowIdx * (DOT + GAP) + DOT / 2;

  // iris: a disc of the Monday-test gradient grows from the "now" dot
  const irisK = interpolate(frame, [190, 250], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.cubic) });
  const irisR = 10 + irisK * 1700;
  const zoom = interpolate(frame, [170, 250], [1, 1.35], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.in(Easing.quad) });
  const endLbl = spring({ frame: frame - (14 + TOTAL * 3), fps, config: { damping: 200 } });

  return (
    <AbsoluteFill style={{ background: `radial-gradient(90% 90% at 70% 15%, ${C.mhHi} 0%, ${C.mhMid} 45%, ${C.midnight} 100%)` }}>
      <Halftone width={SIZE} height={SIZE} step={24} opacity={0.14} />
      <AbsoluteFill style={{ transform: `scale(${zoom})`, transformOrigin: `${nowX}px ${y}px` }}>
        <div style={{ position: "absolute", top: 210, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
          <Caption text="Каждый понедельник — тест." at={4} size={52} out={180} />
          <Caption text="Каждый тест — шаг к цели." at={30} size={52} color={C.cornflower} out={180} />
        </div>

        {Array.from({ length: TOTAL }, (_, i) => {
          const k = spring({ frame: frame - (14 + i * 3), fps, config: { damping: 13, stiffness: 170 } });
          const cx = x0 + i * (DOT + GAP) + DOT / 2;
          const isPast = i < nowIdx, isNow = i === nowIdx;
          let size = DOT, bg = "transparent", border = "3px solid rgba(255,255,255,.45)", opacity = 1, shadow = "none";
          if (isPast) {
            const s = 0.45 + PAST[i] / 180;
            size = DOT * (0.8 + s * 0.5);
            bg = "#fff"; border = "0"; opacity = s;
          }
          if (isNow) {
            const p = (Math.sin((frame / fps) * ((2 * Math.PI) / 2.4)) + 1) / 2; // strip-pulse, 2.4s
            size = DOT * 1.4; bg = "#fff"; border = "0";
            shadow = `0 0 0 ${8 + p * 9}px rgba(255,255,255,${0.22 - p * 0.14})`;
          }
          const label = isPast ? spring({ frame: frame - (60 + i * 6), fps, config: { damping: 200 } }) : 0;
          return (
            <React.Fragment key={i}>
              <div style={{
                position: "absolute", left: cx - size / 2, top: y - size / 2, width: size, height: size, borderRadius: "50%",
                background: bg, border, boxSizing: "border-box", opacity: opacity * k, boxShadow: shadow, transform: `scale(${k})`,
              }} />
              {isPast && (
                <div style={{
                  position: "absolute", left: cx - 40, width: 80, top: y - 64 - (PAST[i] - 40) * 0.9, textAlign: "center",
                  font: `600 20px/1 ${F.mono}`, color: C.heroMuted, opacity: label, transform: `translateY(${(1 - label) * 10}px)`,
                }}>{PAST[i]}%</div>
              )}
            </React.Fragment>
          );
        })}
        {/* rising line through the past scores */}
        <svg width={SIZE} height={SIZE} style={{ position: "absolute", inset: 0 }}>
          <polyline
            points={PAST.map((s, i) => `${x0 + i * (DOT + GAP) + DOT / 2},${y - 74 - (s - 40) * 0.9}`).join(" ")}
            fill="none" stroke={C.cornflower} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"
            strokeDasharray={600}
            strokeDashoffset={interpolate(frame, [70, 130], [600, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
            opacity={0.7}
          />
        </svg>
        <div style={{
          position: "absolute", left: x0 + rowW + 18, top: y - 12, font: `700 22px/1 ${F.body}`, letterSpacing: ".1em",
          textTransform: "uppercase", color: C.heroMuted, opacity: endLbl,
        }}>экзамен</div>
        <div style={{
          position: "absolute", left: nowX - 120, width: 240, top: y + 40, textAlign: "center",
          font: `700 22px/1 ${F.body}`, color: "#fff", opacity: spring({ frame: frame - 110, fps, config: { damping: 200 } }),
        }}>эта неделя</div>
      </AbsoluteFill>

      {irisK > 0 && (
        <div style={{
          // the zoom's transform-origin is the "now" dot, so it stays put on screen
          position: "absolute", left: nowX - irisR, top: y - irisR,
          width: irisR * 2, height: irisR * 2, borderRadius: "50%", background: MH_BG,
        }} />
      )}
    </AbsoluteFill>
  );
};
