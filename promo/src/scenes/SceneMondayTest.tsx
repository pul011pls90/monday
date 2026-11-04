import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, F, MH_BG, SIZE } from "../theme";
import { DipoleField } from "../components/DipoleField";
import { PixelText, pixelWidth } from "../components/PixelText";
import { Cursor } from "../components/Cursor";

/* 0:08–0:13 · The Monday-test hero (templates/student/monday.html, .mh in brand.css).
   "До старта" countdown 00·00·00·03 → 0 in pixel cells, then the scene switches from
   "before" (calm, speed .7) to "live" (speed 1.5, pulse), "● Идёт сейчас", and the CTA gets tapped. */
const GO = 112; // the frame the test opens
const TICKS = [40, 64, 88, GO];

export const SceneMondayTest: React.FC<{ name: string; exam: string }> = ({ name, exam }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const live = frame >= GO;
  // before → live: speed .7 → 1.5, accumulated so the field never jumps
  const time = (0.7 * frame + 0.8 * Math.max(0, frame - GO)) / fps + 4;
  const intensity = interpolate(frame, [0, GO, GO + 20], [0.75, 0.75, 1.05], { extrapolateRight: "clamp" });

  const sp = (at: number, damping = 200) => spring({ frame: frame - at, fps, config: { damping } });
  // 03 → 02 → 01 → 00, then the test opens at GO
  const secLeft = 3 - TICKS.slice(0, 3).filter((t) => frame >= t).length;
  const tickPop = TICKS.reduce((m, t) => (frame >= t && frame < t + 12 ? 1 - (frame - t) / 12 : m), 0);

  const countOut = interpolate(frame, [GO, GO + 14], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const liveIn = sp(GO + 4, 12);
  const ctaIn = sp(GO + 24, 14);
  const TAP = 250;
  const press = interpolate(frame - TAP, [-6, 0, 10], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const outZoom = interpolate(frame, [TAP + 10, 320], [1, 1.12], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const livePulse = (frame % 96) / 96; // mh-pulse 1.6s

  const cell = (label: string, value: string, i: number) => (
    <div key={label} style={{
      minWidth: 118, padding: "16px 16px 12px", borderRadius: 18, background: "rgba(7,15,77,.5)", backdropFilter: "blur(6px)",
      border: "1px solid rgba(255,255,255,.14)", display: "flex", flexDirection: "column", alignItems: "center", gap: 10,
      transform: `translateY(${(1 - sp(20 + i * 4, 14)) * 30}px) scale(${label === "сек" ? 1 + tickPop * 0.08 : 1})`, opacity: sp(20 + i * 4),
    }}>
      <div style={{ width: pixelWidth(value, 9), height: 63 }}>
        <PixelText text={value} cell={9} glow={label === "сек"} />
      </div>
      <span style={{ font: `600 15px/1 ${F.body}`, letterSpacing: ".08em", textTransform: "uppercase", color: "rgba(255,255,255,.65)" }}>{label}</span>
    </div>
  );

  return (
    <AbsoluteFill style={{ background: MH_BG, overflow: "hidden" }}>
      <AbsoluteFill style={{ transform: `scale(${outZoom})` }}>
        <div style={{ position: "absolute", left: 230, top: 40, width: SIZE, height: SIZE, opacity: 0.85 }}>
          <DipoleField width={SIZE} height={SIZE} time={time} intensity={intensity} pulseAt={GO} />
        </div>
        {/* film grain veil so the text keeps contrast, like .mh__canvas at .75–.85 opacity */}
        <AbsoluteFill style={{ background: "linear-gradient(90deg, rgba(7,15,77,.78) 0%, rgba(7,15,77,.35) 55%, rgba(7,15,77,0) 100%)" }} />

        <div style={{ position: "absolute", left: 80, top: 110, right: 80, display: "flex", flexDirection: "column", gap: 28, color: "#fff" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, opacity: sp(0) }}>
            <span style={{ font: `700 20px/1 ${F.body}`, letterSpacing: ".1em", textTransform: "uppercase", color: "rgba(255,255,255,.78)" }}>Ритуал недели · трек {exam}</span>
            <span style={{ padding: "7px 14px", borderRadius: 999, border: "1.5px solid rgba(255,255,255,.3)", font: `700 18px/1 ${F.body}` }}>Неделя 2</span>
          </div>
          <div style={{ font: `800 104px/.98 ${F.display}`, letterSpacing: "-.02em", textShadow: "0 2px 24px rgba(7,15,77,.6)" }}>
            {["Тест", "понедельника"].map((w, i) => {
              const k = sp(4 + i * 8, 15);
              return <div key={w} style={{ overflow: "hidden", paddingBottom: 8 }}><div style={{ transform: `translateY(${(1 - k) * 120}px)` }}>{w}</div></div>;
            })}
          </div>

          {/* status pill: "До старта" → white "● Идёт сейчас" */}
          <div style={{ position: "relative", height: 50 }}>
            <span style={{
              position: "absolute", display: "inline-flex", alignItems: "center", gap: 10, padding: "12px 20px", borderRadius: 999,
              background: "rgba(255,255,255,.12)", font: `700 22px/1 ${F.body}`, opacity: sp(14) * countOut,
            }}>До старта · пн, 19:00</span>
            {live && (
              <span style={{
                position: "absolute", display: "inline-flex", alignItems: "center", gap: 12, padding: "12px 22px", borderRadius: 999,
                background: "#fff", color: C.mhMid, font: `800 24px/1 ${F.body}`, transform: `scale(${0.6 + liveIn * 0.4})`, transformOrigin: "left center", opacity: liveIn,
              }}>
                <i style={{
                  width: 14, height: 14, borderRadius: "50%", background: C.live, display: "inline-block",
                  boxShadow: `0 0 0 ${livePulse * 14}px rgba(229,72,77,${0.7 * (1 - livePulse)})`,
                }} />
                Идёт сейчас
              </span>
            )}
          </div>

          {/* countdown cells → meta + CTA */}
          <div style={{ position: "relative", height: 150 }}>
            <div style={{ position: "absolute", display: "flex", gap: 14, opacity: countOut }}>
              {cell("дн", "00", 0)}{cell("ч", "00", 1)}{cell("мин", "00", 2)}{cell("сек", `0${secLeft}`, 3)}
            </div>
            {live && (
              <div style={{ position: "absolute", display: "flex", flexDirection: "column", gap: 26 }}>
                <span style={{ font: `500 26px/1.3 ${F.body}`, color: "rgba(255,255,255,.82)", opacity: sp(GO + 14), transform: `translateY(${(1 - sp(GO + 14)) * 16}px)` }}>
                  20 минут · 10 задач, одинаковых для всех
                </span>
                <span style={{
                  alignSelf: "flex-start", display: "inline-flex", alignItems: "center", gap: 14, padding: "22px 34px", borderRadius: 16,
                  background: "#fff", color: C.text, font: `700 28px/1 ${F.body}`,
                  boxShadow: `0 0 0 ${8 + 6 * Math.sin(frame / 10)}px rgba(255,255,255,.12)`,
                  transform: `scale(${(0.7 + ctaIn * 0.3) * (1 - press * 0.06)})`, transformOrigin: "left center", opacity: ctaIn,
                }}>
                  Начать тест <span style={{ fontSize: 30 }}>→</span>
                </span>
              </div>
            )}
          </div>
        </div>

        <p style={{
          position: "absolute", right: 60, bottom: 54, margin: 0, maxWidth: 520, textAlign: "right",
          font: `600 26px/1.3 ${F.body}`, color: "rgba(255,255,255,.88)", opacity: sp(GO + 50), transform: `translateY(${(1 - sp(GO + 50)) * 14}px)`,
        }}>Тест открыт. Вперёд, {name}!</p>
      </AbsoluteFill>
      <Cursor appearAt={190} hideAt={300} path={[{ f: 190, x: 760, y: 980 }, { f: 236, x: 230, y: 585 }, { f: TAP, x: 230, y: 585, tap: true }]} />
    </AbsoluteFill>
  );
};
