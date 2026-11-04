import React from "react";
import { AbsoluteFill, interpolate, random, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, CARD_SHADOW, F, SIZE } from "../theme";
import { Tex } from "../components/Tex";
import { Cursor, CursorKey } from "../components/Cursor";
import { PixelText, pixelWidth } from "../components/PixelText";
import { Caption } from "../components/Brand";

/* 0:13–0:20 · Solving. Rebuilt from the test player (bank_play.html / macros.option_inputs):
   session bar, SAT-style option rows with circled letters, "Исключить" strike-out, "Проверить",
   .is-correct (green border + soft green + filled letter) and the "Верно!" feedback line.
   Ends on the q-grid (green = верно, red = неверно) and the score. */

type Q = { text: string; opts: string[]; correct: number; strike?: number; start: number; pick: number; check: number };
const L = ["A", "B", "C", "D"];
const QS: Q[] = [
  { text: "\\text{Вычислите: } \\frac{1}{2} + \\frac{1}{3}", opts: ["\\frac{5}{3}", "\\frac{11}{6}", "\\frac{5}{6}", "\\frac{6}{5}"], correct: 2, strike: 0, start: 0, pick: 64, check: 88 },
  { text: "\\text{Решите: } 2x - 3 = 7", opts: ["x = 2", "x = 5", "x = 4", "x = 10"], correct: 1, start: 136, pick: 168, check: 188 },
  { text: "\\text{Найдите: } \\sqrt{49} + 2^3", opts: ["13", "15", "11", "17"], correct: 1, start: 246, pick: 274, check: 292 },
];
const CARD = { x: 90, y: 190, w: 900, h: 660 };
const optY = (i: number) => CARD.y + 230 + i * 104; // top of option row i
const OPT_H = 88;
const CHECK = { x: 735, y: 905 }; // centre of "Проверить"
const GRID_AT = 350;

const QuestionCard: React.FC<{ q: Q; idx: number; frame: number; fps: number }> = ({ q, idx, frame, fps }) => {
  const f = frame - q.start;
  const next = QS[idx + 1];
  const inK = idx === 0 ? 1 : spring({ frame: f, fps, config: { damping: 18, stiffness: 140 } });
  const outK = next ? spring({ frame: frame - (next.start - 2), fps, config: { damping: 18, stiffness: 140 } }) : spring({ frame: frame - GRID_AT, fps, config: { damping: 200 } });
  const x = (1 - inK) * 1000 - outK * 1000;
  const picked = frame >= q.pick;
  const checked = frame >= q.check;
  const okPop = spring({ frame: frame - q.check, fps, config: { damping: 9, stiffness: 200 } });
  const strikeK = q.strike !== undefined ? interpolate(frame, [36, 48], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;

  return (
    <div style={{
      position: "absolute", left: CARD.x, top: CARD.y, width: CARD.w, height: CARD.h, transform: `translateX(${x}px) rotate(${-outK * 4}deg)`,
      background: "rgba(255,255,255,.96)", borderRadius: 26, boxShadow: CARD_SHADOW + ", 0 30px 80px rgba(21,56,147,.14)", border: `1px solid ${C.line}`,
    }}>
      {/* q-head */}
      <div style={{ position: "absolute", left: 40, top: 34, display: "flex", alignItems: "center", gap: 18 }}>
        <span style={{ width: 52, height: 52, borderRadius: 14, background: C.bar, color: "#fff", display: "grid", placeItems: "center", font: `800 26px/1 ${F.body}` }}>{idx + 1}</span>
        <span style={{ font: `600 20px/1 ${F.body}`, color: C.muted }}>Исключить</span>
        <span style={{ font: `600 20px/1 ${F.body}`, color: C.muted, marginLeft: 8 }}>Попытки <b style={{ marginLeft: 6, padding: "3px 9px", borderRadius: 8, background: C.surface2, color: C.text }}>{checked ? 1 : 0}</b></span>
      </div>
      <div style={{ position: "absolute", left: 40, right: 40, top: 120, color: C.text, fontFamily: F.body }}>
        <Tex tex={q.text} style={{ fontSize: 46 }} />
      </div>
      {q.opts.map((o, i) => {
        const sel = picked && i === q.correct;
        const ok = checked && i === q.correct;
        const struck = i === q.strike;
        const selK = sel ? spring({ frame: frame - q.pick, fps, config: { damping: 12, stiffness: 220 } }) : 0;
        const border = ok ? `3px solid ${C.ok}` : sel ? `3px solid ${C.text}` : `1.5px solid ${C.line}`;
        return (
          <div key={i} style={{
            position: "absolute", left: 40, right: 40, top: optY(i) - CARD.y, height: OPT_H, borderRadius: 16, border, boxSizing: "border-box",
            background: ok ? C.okSoft : "#fff", display: "flex", alignItems: "center", gap: 22, padding: "0 26px",
            transform: `scale(${1 + selK * 0.015 - (sel ? 0 : 0) + (ok ? okPop * 0.02 - 0.0 : 0)})`, opacity: struck ? 1 - strikeK * 0.55 : 1,
          }}>
            <span style={{
              width: 46, height: 46, borderRadius: "50%", border: `2.5px solid ${ok ? C.ok : C.text}`, background: ok ? C.ok : "transparent",
              color: ok ? "#fff" : C.text, display: "grid", placeItems: "center", font: `800 20px/1 ${F.body}`, flex: "none",
            }}>{ok ? "✓" : L[i]}</span>
            <Tex tex={o} style={{ fontSize: 40, color: C.text }} />
            {ok && <span style={{ marginLeft: "auto", font: `800 22px/1 ${F.body}`, color: C.ok, opacity: okPop }}>Верно</span>}
            {struck && <div style={{ position: "absolute", left: 18, top: OPT_H / 2 - 1.5, height: 3, width: `${strikeK * 94}%`, background: C.text, borderRadius: 2 }} />}
          </div>
        );
      })}
    </div>
  );
};

export const SceneSolve: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const current = QS.reduce((c, q, i) => (frame >= q.start ? i : c), 0);
  const q = QS[current];
  const checked = frame >= q.check && frame < GRID_AT;
  const fb = spring({ frame: frame - q.check, fps, config: { damping: 11, stiffness: 200 } });
  const btnPress = interpolate(frame - q.check, [-6, 0, 10], [0, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const solved = QS.filter((x) => frame >= x.check).length;
  const timer = Math.max(0, 20 * 60 - 3 - Math.floor(frame / fps) * 7); // the clock flies: ~7 s per real second
  const uiOut = spring({ frame: frame - GRID_AT, fps, config: { damping: 200 } });

  const path: CursorKey[] = [{ f: 10, x: 980, y: 1060 }];
  QS.forEach((x) => {
    if (x.strike !== undefined) path.push({ f: 30, x: 820, y: optY(x.strike) + OPT_H / 2 }, { f: 40, x: 820, y: optY(x.strike) + OPT_H / 2, tap: true });
    path.push({ f: x.pick - 14, x: 360, y: optY(x.correct) + OPT_H / 2 }, { f: x.pick, x: 360, y: optY(x.correct) + OPT_H / 2, tap: true });
    path.push({ f: x.check - 12, x: CHECK.x, y: CHECK.y }, { f: x.check, x: CHECK.x, y: CHECK.y, tap: true });
  });

  // confetti-ish burst of brand squares on each correct answer
  const burst = (at: number, cx: number, cy: number, key: string) => {
    const d = frame - at;
    if (d < 0 || d > 40) return null;
    return Array.from({ length: 18 }, (_, i) => {
      const a = random(`${key}a${i}`) * Math.PI * 2, v = 6 + random(`${key}v${i}`) * 9, s = 8 + random(`${key}s${i}`) * 10;
      const x = cx + Math.cos(a) * v * d, y = cy + Math.sin(a) * v * d + 0.18 * d * d;
      const col = [C.ok, C.electric, C.cornflower, "#4CB782"][i % 4];
      return <div key={`${key}${i}`} style={{ position: "absolute", left: x, top: y, width: s, height: s, borderRadius: 2, background: col, opacity: 1 - d / 40, transform: `rotate(${d * 12 + i * 30}deg)` }} />;
    });
  };

  // q-grid: a clean 10/10 (staged), so the climb onto the podium in the next scene is earned —
  // the real top 3 in the demo data all have 10/10
  const GRID = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1];
  const score = GRID.slice(0, Math.max(0, Math.min(10, Math.floor((frame - GRID_AT - 10) / 5) + 1))).filter(Boolean).length;

  return (
    <AbsoluteFill style={{ background: "radial-gradient(1000px 600px at 100% -10%, #EAF0FA 0%, rgba(234,240,250,0) 70%), linear-gradient(160deg, #FFFFFF 0%, #F7F8FB 45%, #EEF1F6 100%)" }}>
      {/* session bar (partials/session_bar.html) */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0, height: 120, background: C.bar, color: "#fff", display: "flex", alignItems: "center", padding: "0 56px", gap: 24,
        transform: `translateY(${-uiOut * 140}px)`,
      }}>
        <span style={{ font: `700 24px/1 ${F.body}` }}>Тест понедельника</span>
        <div style={{ display: "flex", gap: 6, flex: 1, marginLeft: 10 }}>
          {Array.from({ length: 10 }, (_, i) => (
            <i key={i} style={{ flex: 1, height: 10, borderRadius: 5, background: i < solved ? C.cornflower : i === solved ? "rgba(255,255,255,.55)" : "rgba(255,255,255,.18)" }} />
          ))}
        </div>
        <span style={{ font: `600 26px/1 ${F.mono}`, fontVariantNumeric: "tabular-nums" }}>⏱ {String(Math.floor(timer / 60)).padStart(2, "0")}:{String(timer % 60).padStart(2, "0")}</span>
      </div>

      {QS.map((x, i) => (Math.abs(i - current) <= 1 ? <QuestionCard key={i} q={x} idx={i} frame={frame} fps={fps} /> : null))}

      {/* foot: feedback + Проверить */}
      <div style={{ position: "absolute", left: CARD.x, right: CARD.x, top: 870, height: 72, display: "flex", alignItems: "center", justifyContent: "space-between", opacity: 1 - uiOut, transform: `translateY(${uiOut * 60}px)` }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 12, font: `800 34px/1 ${F.body}`, color: C.ok, opacity: checked ? fb : 0, transform: `scale(${0.6 + 0.4 * fb})`, transformOrigin: "left center" }}>
          <span style={{ width: 44, height: 44, borderRadius: "50%", background: C.ok, color: "#fff", display: "grid", placeItems: "center", fontSize: 24 }}>✓</span>
          Верно!
        </span>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 10, padding: "22px 34px", borderRadius: 14, background: C.btn, color: "#fff",
          font: `700 26px/1 ${F.body}`, transform: `scale(${1 - btnPress * 0.06})`,
        }}>✓ Проверить</span>
      </div>
      {QS.map((x, i) => <React.Fragment key={i}>{burst(x.check, 200, 905, `b${i}`)}</React.Fragment>)}

      {/* q-grid summary */}
      {frame >= GRID_AT && (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 44 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 120px)", gap: 18 }}>
            {GRID.map((g, i) => {
              const k = spring({ frame: frame - GRID_AT - 10 - i * 5, fps, config: { damping: 11, stiffness: 200 } });
              return (
                <div key={i} style={{
                  width: 120, height: 120, borderRadius: 20, background: g ? C.ok : C.bad, color: "#fff", display: "grid", placeItems: "center",
                  font: `800 40px/1 ${F.body}`, transform: `scale(${k}) translateY(${(1 - k) * 40}px)`, opacity: Math.min(1, k * 1.5), boxShadow: "0 12px 30px rgba(14,14,14,.12)",
                }}>{i + 1}</div>
              );
            })}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
            <div style={{ width: pixelWidth(`${score}/10`, 14), height: 98 }}>
              <PixelText text={`${score}/10`} cell={14} lit={C.bar} unlit="rgba(10,26,92,.07)" />
            </div>
            <span style={{ font: `700 30px/1.2 ${F.body}`, color: C.text2, opacity: spring({ frame: frame - GRID_AT - 50, fps, config: { damping: 200 } }) }}>верно</span>
          </div>
          <Caption text="Ответ и разбор — сразу." at={GRID_AT + 40} size={46} color={C.bar} />
        </AbsoluteFill>
      )}

      <Cursor path={path} appearAt={10} hideAt={GRID_AT - 10} />
    </AbsoluteFill>
  );
};
