import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, F, HEIGHT, SPRINGS, WIDTH } from "../../theme";
import { KineticCaption } from "../shared/KineticCaption";
import { SafeZone } from "../shared/SafeZone";
import { TouchIndicator, TouchWaypoint } from "../shared/TouchIndicator";

interface SkillBranch {
  title: string;
  progress: string;
  totalDots: number;
  masteredDots: number;
  inProgressDots: number;
  isWeakSpot?: boolean;
}

const SKILL_BRANCHES: SkillBranch[] = [
  {
    title: "Арифметика",
    progress: "4/13",
    totalDots: 13,
    masteredDots: 4,
    inProgressDots: 3,
  },
  {
    title: "Алгебра",
    progress: "3/16 · слабое место",
    totalDots: 16,
    masteredDots: 3,
    inProgressDots: 2,
    isWeakSpot: true,
  },
  {
    title: "Функции",
    progress: "1/11",
    totalDots: 11,
    masteredDots: 1,
    inProgressDots: 3,
  },
  {
    title: "Геометрия",
    progress: "2/14",
    totalDots: 14,
    masteredDots: 2,
    inProgressDots: 2,
  },
  {
    title: "Тригонометрия",
    progress: "3/10",
    totalDots: 10,
    masteredDots: 3,
    inProgressDots: 2,
  },
];

export const Block5SkillMap: React.FC = () => {
  const frame = useCurrentFrame(); // Local 0..840 (Global 2160..3000)
  const { fps } = useVideoConfig();

  // Entry spring for Skill Map Grid (Local 0–180)
  const gridEnter = spring({
    frame: frame - 6,
    fps,
    config: SPRINGS.snap,
  });

  // 3D Parallax Dive (Local 200–360 | Global 2360–2520)
  // Camera scales from 1 to 4 directly toward the "Алгебра (слабое место)" node using SPRINGS.soft
  const zoomSpring = spring({
    frame: frame - 205,
    fps,
    config: SPRINGS.soft,
  });

  const cameraScale = 1 + zoomSpring * 3; // 1 -> 4
  // Target focal point of the weak-spot dot inside the Алгебра card: (510, 560)
  const focalX = 510;
  const focalY = 560;
  const cameraTranslateX = (WIDTH / 2 - focalX) * zoomSpring;
  const cameraTranslateY = (HEIGHT * 0.45 - focalY) * zoomSpring;

  // Parallax layers moving at 0.3x and 0.6x speed
  const parallax03X = cameraTranslateX * 0.3;
  const parallax03Y = cameraTranslateY * 0.3;
  const parallax06X = cameraTranslateX * 0.6;
  const parallax06Y = cameraTranslateY * 0.6;

  // Subtle depth-of-field blur on outer cards during dive
  const outerCardBlur = interpolate(zoomSpring, [0, 1], [0, 6], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Modal Growth Directly Out of the Tapped Problem Node (Local 360–840 | Global 2520–3000) using SPRINGS.snap
  const modalGrow = spring({
    frame: frame - 360,
    fps,
    config: SPRINGS.snap,
  });

  // Touch Indicator Waypoints: Tap weak spot node at Local 355 (Global 2515), then tap YouTube Play at Local 550 (Global 2710)
  const touchWaypoints: TouchWaypoint[] = [
    { frame: 290, x: 680, y: 920 },
    { frame: 355, x: 540, y: 864 }, // Taps zoomed weak-spot node
    { frame: 460, x: 640, y: 1020 },
    { frame: 550, x: 495, y: 985 }, // Taps YouTube Play button
    { frame: 610, x: 640, y: 1080 },
  ];

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Parallax Background Layer 1 (0.3x speed) */}
      <div
        style={{
          position: "absolute",
          inset: -120,
          transform: `translate(${parallax03X}px, ${parallax03Y}px) scale(${
            1 + zoomSpring * 0.35
          })`,
          pointerEvents: "none",
          opacity: 0.35,
        }}
      >
        <svg width={WIDTH + 240} height={HEIGHT + 240}>
          <g stroke="rgba(99, 102, 241, 0.22)" strokeWidth={1.5} fill="none">
            <circle cx={660} cy={680} r={220} strokeDasharray="8 12" />
            <circle cx={660} cy={680} r={380} strokeDasharray="4 16" />
            <path d="M 180 420 L 660 680 L 960 520" />
          </g>
        </svg>
      </div>

      {/* Parallax Midground Layer 2 (0.6x speed) */}
      <div
        style={{
          position: "absolute",
          inset: -80,
          transform: `translate(${parallax06X}px, ${parallax06Y}px) scale(${
            1 + zoomSpring * 0.75
          })`,
          pointerEvents: "none",
          opacity: 0.45,
        }}
      >
        <svg width={WIDTH + 160} height={HEIGHT + 160}>
          <g fill={COLORS.indigo}>
            <circle cx={310} cy={520} r={5} opacity={0.5} />
            <circle cx={820} cy={610} r={6} opacity={0.5} />
            <circle cx={420} cy={920} r={5} opacity={0.5} />
            <circle cx={760} cy={880} r={7} opacity={0.5} />
          </g>
        </svg>
      </div>

      {/* Foreground 1.0x Camera Rig (Scales 1 -> 4 into Алгебра weak spot node) */}
      <AbsoluteFill
        style={{
          transformOrigin: `${focalX}px ${focalY}px`,
          transform: `translate(${cameraTranslateX}px, ${cameraTranslateY}px) scale(${cameraScale})`,
          opacity: 1 - modalGrow * 0.88,
        }}
      >
        <SafeZone justify="flex-start" style={{ gap: 14 }}>
          {/* Skill Map Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "16px 22px",
              borderRadius: 22,
              backgroundColor: COLORS.surface,
              border: `1px solid ${COLORS.surfaceBorder}`,
              filter: outerCardBlur > 0.4 ? `blur(${outerCardBlur * 0.5}px)` : undefined,
              opacity: gridEnter,
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: F.mono,
                  fontSize: 16,
                  color: COLORS.indigo,
                  letterSpacing: "0.08em",
                }}
              >
                ДИАГНОСТИКА И ПРОГРЕСС · КАРТА НАВЫКОВ
              </div>
              <div
                style={{
                  fontFamily: F.display,
                  fontSize: 28,
                  fontWeight: 800,
                  color: "#FFFFFF",
                }}
              >
                Карта навыков
              </div>
            </div>

            {/* Legend Pills: Освоен / В процессе / Слабое место */}
            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 11,
                    height: 11,
                    borderRadius: "50%",
                    backgroundColor: COLORS.brandBlueBright,
                  }}
                />
                <span style={{ fontFamily: F.mono, fontSize: 14, color: "#CBD5E1" }}>
                  Освоен
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    width: 11,
                    height: 11,
                    borderRadius: "50%",
                    backgroundColor: COLORS.indigo,
                  }}
                />
                <span style={{ fontFamily: F.mono, fontSize: 14, color: "#CBD5E1" }}>
                  В процессе
                </span>
              </div>
            </div>
          </div>

          {/* Skill Map Cards List */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {SKILL_BRANCHES.map((branch, bIdx) => {
              const isAlgebra = !!branch.isWeakSpot;
              const branchEnter = spring({
                frame: frame - (16 + bIdx * 6),
                fps,
                config: SPRINGS.snap,
              });

              return (
                <div
                  key={branch.title}
                  style={{
                    borderRadius: 22,
                    padding: "16px 22px",
                    backgroundColor: isAlgebra
                      ? "rgba(30, 58, 138, 0.34)"
                      : COLORS.surface,
                    border: `1.5px solid ${
                      isAlgebra ? COLORS.coral : COLORS.surfaceBorder
                    }`,
                    boxShadow: isAlgebra
                      ? "0 14px 40px rgba(244, 63, 94, 0.22)"
                      : "none",
                    filter:
                      !isAlgebra && outerCardBlur > 0.4
                        ? `blur(${outerCardBlur.toFixed(1)}px)`
                        : undefined,
                    opacity: branchEnter,
                    transform: `translateY(${(1 - branchEnter) * 24}px)`,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: 12,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span
                        style={{
                          fontFamily: F.display,
                          fontSize: 22,
                          fontWeight: 800,
                          color: "#FFFFFF",
                        }}
                      >
                        {branch.title}
                      </span>
                      {isAlgebra && (
                        <span
                          style={{
                            padding: "4px 12px",
                            borderRadius: 999,
                            backgroundColor: "rgba(244, 63, 94, 0.2)",
                            border: `1px solid ${COLORS.coral}`,
                            fontFamily: F.mono,
                            fontSize: 14,
                            fontWeight: 700,
                            color: COLORS.coral,
                          }}
                        >
                          СЛАБОЕ МЕСТО
                        </span>
                      )}
                    </div>

                    <span
                      style={{
                        fontFamily: F.mono,
                        fontSize: 18,
                        fontWeight: 700,
                        color: isAlgebra ? COLORS.coral : "#93C5FD",
                      }}
                    >
                      {branch.progress}
                    </span>
                  </div>

                  {/* Sequential Skill Dots Row */}
                  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    {Array.from({ length: branch.totalDots }, (_, dIdx) => {
                      const lightFrame = 35 + bIdx * 10 + dIdx * 5;
                      const dotPop = spring({
                        frame: frame - lightFrame,
                        fps,
                        config: SPRINGS.bounce,
                      });

                      const isMastered = dIdx < branch.masteredDots;
                      const isInProgress =
                        dIdx >= branch.masteredDots &&
                        dIdx < branch.masteredDots + branch.inProgressDots;
                      const isWeakTarget = isAlgebra && dIdx === 5;

                      let bg = "rgba(255, 255, 255, 0.1)";
                      let border = "rgba(255, 255, 255, 0.16)";
                      let glow = "none";

                      if (frame >= lightFrame) {
                        if (isWeakTarget) {
                          bg = COLORS.coral;
                          border = "#FFFFFF";
                          glow = `0 0 18px ${COLORS.coral}`;
                        } else if (isMastered) {
                          bg = COLORS.brandBlueBright; // Освоен (deep/primary blue)
                          border = "#93C5FD";
                          glow = `0 0 12px ${COLORS.brandBlueBright}`;
                        } else if (isInProgress) {
                          bg = COLORS.indigo; // В процессе (pulsing indigo)
                          border = "#C7D2FE";
                          glow = `0 0 ${10 + Math.sin(frame * 0.18) * 6}px ${COLORS.indigo}`;
                        }
                      }

                      return (
                        <div
                          key={dIdx}
                          style={{
                            width: isWeakTarget ? 28 : 22,
                            height: isWeakTarget ? 28 : 22,
                            borderRadius: "50%",
                            backgroundColor: bg,
                            border: `2px solid ${border}`,
                            boxShadow: glow,
                            transform: `scale(${
                              frame >= lightFrame ? 0.6 + dotPop * 0.4 : 0.85
                            })`,
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </SafeZone>
      </AbsoluteFill>

      {/* EXPLANATION MODAL GROWING DIRECTLY OUT OF TAPPED NODE + YOUTUBE VIDEO REVIEW (Local 360–840 | Global 2520–3000) */}
      <SafeZone justify="space-between">
        {frame >= 356 ? (
          <div
            style={{
              borderRadius: 30,
              padding: "24px 26px",
              backgroundColor: "rgba(11, 15, 25, 0.94)",
              border: `2px solid ${COLORS.indigo}`,
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              boxShadow: "0 32px 90px rgba(0, 0, 0, 0.78)",
              transformOrigin: "50% 38%",
              transform: `scale(${modalGrow})`,
              opacity: modalGrow,
              display: "flex",
              flexDirection: "column",
              gap: 16,
              zIndex: 35,
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: `1px solid ${COLORS.surfaceBorder}`,
                paddingBottom: 12,
              }}
            >
              <div>
                <span
                  style={{
                    fontFamily: F.mono,
                    fontSize: 16,
                    fontWeight: 700,
                    color: COLORS.coral,
                    letterSpacing: "0.06em",
                  }}
                >
                  УЗЕЛ НАВЫКА · АЛГЕБРА 3/16 · ЗАКРЫТИЕ ПРОБЕЛА
                </span>
                <div
                  style={{
                    fontFamily: F.display,
                    fontSize: 25,
                    fontWeight: 800,
                    color: "#FFFFFF",
                    marginTop: 2,
                  }}
                >
                  Квадратичные неравенства и парабола
                </div>
              </div>
              <div
                style={{
                  padding: "6px 14px",
                  borderRadius: 999,
                  backgroundColor: "rgba(16, 185, 129, 0.18)",
                  border: `1px solid ${COLORS.emerald}`,
                  fontFamily: F.mono,
                  fontSize: 15,
                  fontWeight: 700,
                  color: COLORS.emerald,
                }}
              >
                РАЗБОР + ВИДЕО
              </div>
            </div>

            {/* Algebraic Derivation + Clean Geometric Diagram Side-by-Side */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1.15fr 0.85fr",
                gap: 16,
              }}
            >
              {/* Algebraic Derivation */}
              <div
                style={{
                  padding: "16px 18px",
                  borderRadius: 20,
                  backgroundColor: "rgba(15, 23, 42, 0.85)",
                  border: `1px solid ${COLORS.surfaceBorder}`,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <span
                  style={{
                    fontFamily: F.mono,
                    fontSize: 15,
                    color: "#93C5FD",
                    fontWeight: 600,
                  }}
                >
                  АЛГЕБРАИЧЕСКИЙ ВЫВОД
                </span>
                <div
                  style={{
                    fontFamily: F.mono,
                    fontSize: 20,
                    color: "#F8FAFC",
                    lineHeight: 1.5,
                  }}
                >
                  x² − 5x + 6 ≤ 0
                  <br />
                  (x − 2)(x − 3) ≤ 0
                  <br />
                  Корни: x₁ = 2, x₂ = 3
                  <br />
                  <span style={{ color: COLORS.emerald, fontWeight: 700 }}>
                    Ответ: x ∈ [2; 3]
                  </span>
                </div>
              </div>

              {/* Clean Geometric Diagram */}
              <div
                style={{
                  padding: "14px",
                  borderRadius: 20,
                  backgroundColor: "rgba(15, 23, 42, 0.85)",
                  border: `1px solid ${COLORS.surfaceBorder}`,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg width={280} height={140} viewBox="0 0 280 140">
                  {/* Number axis */}
                  <line
                    x1={20}
                    y1={85}
                    x2={260}
                    y2={85}
                    stroke="#94A3B8"
                    strokeWidth={2.5}
                  />
                  {/* Shaded interval [2, 3] */}
                  <rect
                    x={95}
                    y={81}
                    width={90}
                    height={8}
                    rx={4}
                    fill={COLORS.emerald}
                  />
                  {/* Parabola arch */}
                  <path
                    d="M 45 25 Q 140 155 235 25"
                    fill="none"
                    stroke={COLORS.indigo}
                    strokeWidth={3.5}
                  />
                  {/* Root nodes x=2, x=3 */}
                  <circle cx={95} cy={85} r={7} fill={COLORS.emerald} stroke="#FFF" strokeWidth={2} />
                  <circle cx={185} cy={85} r={7} fill={COLORS.emerald} stroke="#FFF" strokeWidth={2} />
                  <text x={95} y={115} textAnchor="middle" fill="#FFF" style={{ fontFamily: F.mono, fontSize: 18, fontWeight: 700 }}>
                    2
                  </text>
                  <text x={185} y={115} textAnchor="middle" fill="#FFF" style={{ fontFamily: F.mono, fontSize: 18, fontWeight: 700 }}>
                    3
                  </text>
                  <text x={55} y={68} fill="#93C5FD" style={{ fontFamily: F.mono, fontSize: 18, fontWeight: 700 }}>
                    +
                  </text>
                  <text x={140} y={108} textAnchor="middle" fill={COLORS.emerald} style={{ fontFamily: F.mono, fontSize: 20, fontWeight: 700 }}>
                    −
                  </text>
                  <text x={225} y={68} fill="#93C5FD" style={{ fontFamily: F.mono, fontSize: 18, fontWeight: 700 }}>
                    +
                  </text>
                </svg>
              </div>
            </div>

            {/* YouTube Video Explanation Card with Custom Math Thumbnail & Animated Play Button (3 Expanding Pulse Rings) */}
            <div
              style={{
                position: "relative",
                height: 250,
                borderRadius: 22,
                overflow: "hidden",
                background: `linear-gradient(135deg, #0F172A 0%, ${COLORS.brandBlue} 55%, #1E1B4B 100%)`,
                border: `1.5px solid rgba(255, 255, 255, 0.18)`,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0 32px",
              }}
            >
              {/* Decorative Math Grid & Formulas inside Thumbnail */}
              <svg
                width={800}
                height={250}
                viewBox="0 0 800 250"
                style={{
                  position: "absolute",
                  inset: 0,
                  opacity: 0.22,
                  pointerEvents: "none",
                }}
              >
                <circle cx={650} cy={125} r={140} fill="none" stroke={COLORS.indigo} strokeWidth={2} strokeDasharray="6 8" />
                <path
                  d="M 480 210 L 580 55 L 710 210 Z"
                  fill="none"
                  stroke={COLORS.emerald}
                  strokeWidth={3}
                />
              </svg>

              {/* Left Video Metadata */}
              <div style={{ position: "relative", zIndex: 2, maxWidth: 460 }}>
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "5px 12px",
                    borderRadius: 8,
                    backgroundColor: "#EF4444",
                    fontFamily: F.mono,
                    fontSize: 14,
                    fontWeight: 700,
                    color: "#FFFFFF",
                    marginBottom: 12,
                  }}
                >
                  ▶ YOUTUBE ВИДЕО-РАЗБОР · 03:45
                </div>
                <div
                  style={{
                    fontFamily: F.display,
                    fontSize: 24,
                    fontWeight: 800,
                    color: "#FFFFFF",
                    lineHeight: 1.25,
                    marginBottom: 8,
                  }}
                >
                  Метод интервалов за 3 минуты без ошибок со знаками
                </div>
                <div
                  style={{
                    fontFamily: F.body,
                    fontSize: 17,
                    color: "#CBD5E1",
                  }}
                >
                  Привязан прямо к задаче · Таймкод 01:12
                </div>
              </div>

              {/* Right Animated Play Button Emitting 3 Expanding Pulse Rings */}
              <div
                style={{
                  position: "relative",
                  zIndex: 2,
                  width: 140,
                  height: 140,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg
                  width={180}
                  height={180}
                  viewBox="-90 -90 180 180"
                  style={{ overflow: "visible" }}
                >
                  {/* 3 Expanding Pulse Rings */}
                  {[0, 1, 2].map((ringIdx) => {
                    const cycle = ((frame + ringIdx * 20) % 60) / 60; // 0..1
                    const r = 34 + cycle * 48;
                    const op = (1 - cycle) * 0.75;
                    return (
                      <circle
                        key={ringIdx}
                        cx={0}
                        cy={0}
                        r={r}
                        fill="none"
                        stroke={ringIdx % 2 === 0 ? "#EF4444" : COLORS.indigo}
                        strokeWidth={3 * (1 - cycle)}
                        opacity={op}
                      />
                    );
                  })}

                  {/* Core Play Circle */}
                  <circle
                    cx={0}
                    cy={0}
                    r={36}
                    fill="#EF4444"
                    stroke="#FFFFFF"
                    strokeWidth={3}
                  />
                  {/* Play Triangle */}
                  <polygon points="-8,-14 -8,14 16,0" fill="#FFFFFF" />
                </svg>
              </div>
            </div>
          </div>
        ) : (
          <div />
        )}

        {/* Bottom Kinetic Russian Caption */}
        <KineticCaption
          kicker="ТОЧЕЧНОЕ ЗАКРЫТИЕ СЛАБЫХ ТЕМ"
          text="Закрывай пробелы с видео-разборами и картой навыков"
          startFrame={14}
          endFrame={826}
          accentColor={COLORS.coral}
        />
      </SafeZone>

      {/* Sleek Touch Indicator */}
      <TouchIndicator
        waypoints={touchWaypoints}
        tapFrames={[355, 550]}
        visibleRange={[285, 620]}
        accentColor={COLORS.coral}
      />
    </AbsoluteFill>
  );
};
