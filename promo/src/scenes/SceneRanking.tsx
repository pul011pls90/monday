import React from "react";
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";
import { C, CARD_SHADOW, F } from "../theme";
import { PixelText, pixelWidth } from "../components/PixelText";
import { Caption } from "../components/Brand";

/* 0:20–0:26 · The Monday-test ranking (ranking.js + .rk-* in brand.css).
   Podium columns assemble from falling squares (rk-drop, column delays 3rd → 2nd → 1st), 1st place shines (rk-shine),
   rows slide in (rk-row) with score dots popping (rk-dot). Then the student's own bar (rk-me) fills,
   the place rolls #23 → #3, the 3rd column becomes "Ты" and Сезим moves down to row 4.
   Names/regions are the real demo data; Тима's climb is staged. */

const TOP = [
  { place: 1, name: "Айгерим", region: "Бишкек" },
  { place: 2, name: "Эмир", region: "Чуйская область" },
  { place: 3, name: "Сезим", region: "Талас" },
];
const ROWS = [
  { name: "Нурай", region: "Каракол", score: 9 },
  { name: "Бакыт", region: "Чуйская область", score: 9 },
  { name: "Улан", region: "Талас", score: 9 },
];
const CARD = { x: 60, y: 50, w: 960, h: 850 };
const CLIMB = [150, 235]; // frames of the #23 → #3 roll
const SWAP = CLIMB[1];
const ROW_H = 74;

export const SceneRanking: React.FC<{ region: string }> = ({ region }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sp = (at: number, damping = 200, stiffness = 100) => spring({ frame: frame - at, fps, config: { damping, stiffness } });

  const climbK = interpolate(frame, CLIMB, [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const place = Math.round(23 - 20 * climbK);
  const myScore = Math.round(5 + 5 * interpolate(frame, [CLIMB[0], CLIMB[0] + 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const swapped = frame >= SWAP;
  const swapK = sp(SWAP, 10, 180);
  const shift = sp(SWAP, 16, 140); // rows move down one place

  const heights = [7, 9, 5];
  const order = [TOP[1], TOP[0], TOP[2]];
  const colDelay = [16, 32, 0]; // frames: 2nd, 1st, 3rd  (3rd → 2nd → 1st as in CSS)
  const medal = [C.silver, C.gold, C.bronze];
  const shine = ((frame - 100) % 190) / 190; // rk-shine sweep, after the 1st column has landed

  const column = (who: { place: number; name: string; region: string }, k: number) => {
    const h = heights[k], cols = 7, base = 40 + colDelay[k];
    const isMe = who.place === 3 && swapped;
    const sq: React.ReactNode[] = [];
    for (let y = 0; y < h; y++)
      for (let x = 0; x < cols; x++) {
        const d = base + ((h - 1 - y) * 3 + (x % 3)) * 1.3; // 22ms steps at 60fps
        const t = spring({ frame: frame - d, fps, config: { damping: 9, stiffness: 220, mass: 0.5 } });
        const col = who.place === 1 ? "#1d34c4" : who.place === 3 ? (isMe ? C.electric : "#6f86ea") : C.btn;
        sq.push(<i key={`${x}-${y}`} style={{ aspectRatio: "1", borderRadius: 3, background: col, opacity: Math.min(1, t * 1.4), transform: `translateY(${(1 - t) * -30}px)` }} />);
      }
    const whoIn = sp(base + h * 4);
    const pop = isMe ? 1 + 0.12 * Math.sin(Math.min(1, (frame - SWAP) / 24) * Math.PI) : 1;
    return (
      <div key={k} style={{ display: "grid", gap: 12, justifyItems: "center", alignSelf: "end", transform: `scale(${pop})`, transformOrigin: "bottom center" }}>
        <div style={{ display: "grid", justifyItems: "center", gap: 4, opacity: whoIn, transform: `translateY(${(1 - whoIn) * 12}px)` }}>
          <b style={{ font: `800 30px/1.1 ${F.body}`, color: isMe ? C.accent : C.text, opacity: isMe ? swapK : 1 }}>{isMe ? "Ты" : who.name}</b>
          <span style={{ font: `500 19px/1.1 ${F.body}`, color: C.muted }}>{isMe ? region : who.region}</span>
          {isMe && <span style={{ font: `700 18px/1 ${F.mono}`, color: C.ok, opacity: swapK }}>▲20</span>}
        </div>
        <div style={{ width: pixelWidth("10/10", 5), height: 35, opacity: whoIn }}>
          <PixelText text="10/10" cell={5} lit={C.text} unlit="rgba(14,14,14,.08)" />
        </div>
        <div style={{
          position: "relative", width: "100%", display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 5, padding: 10,
          borderRadius: "16px 16px 6px 6px", background: "rgba(39,71,216,.06)", marginTop: 22, overflow: "visible",
        }}>
          {sq}
          <em style={{
            position: "absolute", left: "50%", top: -22, transform: "translateX(-50%)", width: 44, height: 44, borderRadius: "50%", background: "#fff",
            display: "grid", placeItems: "center", font: `700 24px/1 ${F.mono}`, fontStyle: "normal", color: medal[k], boxShadow: "0 2px 10px rgba(14,14,14,.12)", opacity: whoIn,
          }}>{who.place}</em>
          {who.place === 1 && frame > 100 && (
            <div style={{
              position: "absolute", inset: 0, borderRadius: "inherit", pointerEvents: "none", opacity: 0.8,
              background: `linear-gradient(110deg, transparent ${30 + (150 - 200 * shine) - 50}%, rgba(255,255,255,.55) ${50 + (150 - 200 * shine) - 50}%, transparent ${70 + (150 - 200 * shine) - 50}%)`,
            }} />
          )}
        </div>
      </div>
    );
  };

  const dots = (score: number, delay: number) => (
    <span style={{ display: "flex", gap: 5 }}>
      {Array.from({ length: 10 }, (_, i) => {
        const on = i < score;
        const k = on ? sp(delay + i * 2.4, 12, 200) : 1;
        return <i key={i} style={{ width: 12, height: 12, borderRadius: "50%", background: on ? C.accent : C.line, transform: `scale(${0.4 + 0.6 * k})` }} />;
      })}
    </span>
  );

  // rows: after the swap Сезим becomes #4 and everybody shifts down one row
  const rows = [{ name: TOP[2].name, region: TOP[2].region, score: 10 }, ...ROWS];
  const listTop = 520;

  // confetti on the swap
  const confetti = () => {
    const d = frame - SWAP;
    if (d < 0 || d > 70) return null;
    return Array.from({ length: 36 }, (_, i) => {
      const a = -Math.PI / 2 + (random(`ra${i}`) - 0.5) * 2.2, v = 8 + random(`rv${i}`) * 12, s = 9 + random(`rs${i}`) * 9;
      const x = 770 + Math.cos(a) * v * d, y = 300 + Math.sin(a) * v * d + 0.22 * d * d;
      return <div key={i} style={{ position: "absolute", left: x, top: y, width: s, height: s * 0.6, borderRadius: 2, background: [C.electric, C.cornflower, C.gold, C.ok][i % 4], opacity: 1 - d / 70, transform: `rotate(${d * 10 + i * 40}deg)` }} />;
    });
  };

  const cardIn = sp(0, 18, 120);
  return (
    <AbsoluteFill style={{ background: "radial-gradient(1000px 600px at 100% -10%, #EAF0FA 0%, rgba(234,240,250,0) 70%), linear-gradient(160deg, #FFFFFF 0%, #F7F8FB 45%, #EEF1F6 100%)" }}>
      <div style={{
        position: "absolute", left: CARD.x, top: CARD.y, width: CARD.w, height: CARD.h, borderRadius: 28, background: "rgba(255,255,255,.96)",
        border: `1px solid ${C.line}`, boxShadow: CARD_SHADOW + ", 0 30px 80px rgba(21,56,147,.12)", padding: "40px 48px", boxSizing: "border-box",
        transform: `translateY(${(1 - cardIn) * 80}px)`, opacity: cardIn, overflow: "hidden",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ margin: 0, font: `700 34px/1.2 ${F.body}`, color: C.text, letterSpacing: "-.02em" }}>Рейтинг недели</h2>
          <div style={{ display: "flex", padding: 5, borderRadius: 999, background: C.surface2, gap: 2 }}>
            {["Страна", "Область", "Школа"].map((s, i) => (
              <span key={s} style={{ padding: "10px 18px", borderRadius: 999, font: `700 19px/1 ${F.body}`, background: i === 0 ? C.btn : "transparent", color: i === 0 ? "#fff" : C.text2 }}>{s}</span>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 30, alignItems: "end", marginTop: 26, height: 360 }}>
          {order.map((w, k) => column(w, k))}
        </div>

        {/* rows 4..6 */}
        <div style={{ position: "absolute", left: 48, right: 48, top: listTop, height: ROW_H * 3, overflow: "hidden" }}>
          {rows.map((r, i) => {
            const slot = i - 1 + (swapped ? shift : 0); // -1 = hidden above (Сезим before the swap)
            const rowIn = sp(80 + Math.max(0, i - 1) * 3, 200);
            const vis = i === 0 ? (swapped ? shift : 0) : rowIn;
            return (
              <div key={r.name} style={{
                position: "absolute", left: 0, right: 0, top: slot * ROW_H, height: ROW_H, display: "grid", gridTemplateColumns: "56px 1fr auto 70px",
                alignItems: "center", gap: 16, borderTop: `1px solid ${C.line}`, opacity: vis, transform: `translateX(${(1 - rowIn) * -24}px)`,
              }}>
                <span style={{ font: `700 22px/1 ${F.mono}`, color: C.accent }}>{i + 4 - (swapped ? 0 : 1)}</span>
                <span style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                  <b style={{ font: `700 24px/1 ${F.body}`, color: C.text }}>{r.name}</b>
                  <span style={{ font: `500 18px/1 ${F.body}`, color: C.muted }}>{r.region}</span>
                </span>
                {dots(r.score, 100 + i * 3)}
                <span style={{ font: `700 21px/1 ${F.mono}`, textAlign: "right", color: C.text }}>{r.score}/10</span>
              </div>
            );
          })}
        </div>

        {/* rk-me: own row with the gradient fill */}
        <div style={{
          position: "absolute", left: 48, right: 48, top: listTop + ROW_H * 3 + 26, height: 84, borderRadius: 18, overflow: "hidden",
          display: "grid", gridTemplateColumns: "90px 1fr auto 80px", alignItems: "center", gap: 16, padding: "0 24px", boxSizing: "border-box",
          background: "rgba(39,71,216,.08)", color: "#fff", opacity: sp(110), transform: `translateY(${(1 - sp(110)) * 30}px)`,
        }}>
          <div style={{
            position: "absolute", inset: 0, background: "linear-gradient(90deg, #2747d8, #3e5bf0)", transformOrigin: "left",
            transform: `scaleX(${interpolate(myScore, [5, 10], [0.5, 1]) * sp(118, 200, 60)})`, zIndex: 0,
          }} />
          <span style={{ position: "relative", font: `700 30px/1 ${F.mono}` }}>#{place}</span>
          <span style={{ position: "relative", display: "flex", alignItems: "baseline", gap: 10 }}>
            <b style={{ font: `800 26px/1 ${F.body}` }}>Ты</b>
            <span style={{ font: `500 18px/1 ${F.body}`, color: "rgba(255,255,255,.78)" }}>{region}</span>
          </span>
          <span style={{ position: "relative", font: `500 17px/1.2 ${F.mono}`, color: "#dfe5ff" }}>{swapped ? "Ты в тройке!" : `до #${Math.max(3, place - 1)} — 1 зад.`}</span>
          <span style={{ position: "relative", font: `700 26px/1 ${F.mono}`, textAlign: "right" }}>{myScore}/10</span>
        </div>
      </div>
      {confetti()}
      <div style={{ position: "absolute", left: 40, right: 40, top: 932 }}>
        <Caption text="Вся страна решает вместе с тобой." at={36} size={44} color={C.bar} />
      </div>
    </AbsoluteFill>
  );
};
