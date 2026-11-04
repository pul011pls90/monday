import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, F, HEIGHT, SPRINGS, WIDTH } from "../../theme";
import { KineticCaption } from "../shared/KineticCaption";
import { SafeZone } from "../shared/SafeZone";
import { TouchIndicator, TouchWaypoint } from "../shared/TouchIndicator";

const OPTIONS = [
  { id: "А", label: "x = 7", isCorrect: true },
  { id: "Б", label: "x = 5", isCorrect: false },
  { id: "В", label: "x = 9", isCorrect: false },
  { id: "Г", label: "x = 3", isCorrect: false },
];

const COMPETITORS = [
  { name: "Айдана К.", school: "Лицей №61 · Бишкек", xp: "1 940 XP", badge: "ОРТ" },
  { name: "Бекзат М.", school: "НИШ ФМН · Алматы", xp: "1 910 XP", badge: "ЕНТ" },
  { name: "Даниил С.", school: "Физтех-лицей · Москва", xp: "1 885 XP", badge: "ЕГЭ" },
];

export const Block2MondayTest: React.FC = () => {
  const frame = useCurrentFrame(); // Local 0..660 (Global 300..960)
  const { fps } = useVideoConfig();

  // Entry VFX (Global 300–305 | Local 0–5): 5-frame high-energy flash + RGB chromatic aberration (±8px decaying to 0)
  const rgbShift = interpolate(frame, [0, 5], [8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const entryFlashOpacity = interpolate(frame, [0, 5], [0.85, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Rotating conic-gradient angle for the hero banner border
  const conicAngle = (frame * 3.2) % 360;

  // Hero banner entrance
  const heroEnter = spring({
    frame: frame - 2,
    fps,
    config: SPRINGS.snap,
  });

  // Phase 1: Question Card enters at Local 50 (Global 350) with SPRINGS.snap
  const questionEnter = spring({
    frame: frame - 50,
    fps,
    config: SPRINGS.snap,
  });

  // Wrong tap at Local 105 (Global 405) on Option (Б)
  const wrongTapFrame = 105;
  const dtWrong = frame - wrongTapFrame;

  // Strictly deterministic decaying sine wave shake over 18 frames: x = A * Math.sin(f * t) * Math.exp(-k * t)
  let cardShakeX = 0;
  if (dtWrong >= 0 && dtWrong <= 18) {
    const A = 22;
    const freq = 1.65;
    const k = 0.21;
    cardShakeX = A * Math.sin(freq * dtWrong) * Math.exp(-k * dtWrong);
  }

  // Accordion explanation smooth expansion (Local 132 | Global 432) using SPRINGS.soft
  const accordionExpand = spring({
    frame: frame - 132,
    fps,
    config: SPRINGS.soft,
  });

  // Phase 2: Retry & Correct Win at Local 255 (Global 555) on Option (А)
  const rightTapFrame = 255;
  const dtRight = frame - rightTapFrame;

  const emeraldSweep = interpolate(dtRight, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const checkmarkDraw = interpolate(dtRight, [4, 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const xpBounce = spring({
    frame: dtRight - 2,
    fps,
    config: SPRINGS.bounce,
  });

  // 14 radial particles bursting outward with simulated gravity
  const particles = useMemo(() => {
    return Array.from({ length: 14 }, (_, i) => {
      const angle = (i / 14) * Math.PI * 2 - Math.PI / 2;
      const speed = 9 + (i % 3) * 3.5;
      return {
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 4,
        color: i % 2 === 0 ? COLORS.emerald : i % 3 === 0 ? COLORS.indigo : "#FFFFFF",
        size: 6 + (i % 3) * 2.5,
      };
    });
  }, []);

  // Phase 3: Leaderboard Rise (Global 720–960 | Local 420–660)
  const leaderboardPhase = spring({
    frame: frame - 420,
    fps,
    config: SPRINGS.soft,
  });

  // Student climbs from #4 up to #1 across local frames 465..565
  const climbProgress = interpolate(frame, [465, 565], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  const studentRank = Math.max(1, Math.round(4 - climbProgress * 3));
  const studentXP = Math.round(1860 + climbProgress * 140);

  // Touch Indicator Waypoints across Wrong -> Retry
  const touchWaypoints: TouchWaypoint[] = [
    { frame: 75, x: 740, y: 980 },
    { frame: wrongTapFrame, x: 650, y: 780 }, // Option (Б)
    { frame: 165, x: 610, y: 920 }, // Observe explanation
    { frame: rightTapFrame, x: 265, y: 780 }, // Option (А)
    { frame: 310, x: 460, y: 980 },
  ];

  const renderSceneContent = (channelColor?: string) => (
    <SafeZone justify="flex-start" style={{ gap: 20 }}>
      {/* Deep Blue "Тест понедельника" Hero Banner with Rotating Conic-Gradient Border */}
      <div
        style={{
          position: "relative",
          borderRadius: 28,
          padding: 3,
          background: `conic-gradient(from ${conicAngle}deg, ${COLORS.indigo}, ${COLORS.emerald}, ${COLORS.coral}, ${COLORS.indigo})`,
          transform: `scale(${0.92 + heroEnter * 0.08})`,
          opacity: heroEnter,
          boxShadow: "0 20px 55px rgba(30, 58, 138, 0.5)",
        }}
      >
        <div
          style={{
            borderRadius: 25,
            padding: "22px 28px",
            background: `linear-gradient(135deg, ${COLORS.brandBlue} 0%, #0F172A 100%)`,
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span
              style={{
                fontFamily: F.mono,
                fontSize: 18,
                fontWeight: 600,
                letterSpacing: "0.08em",
                color: "#93C5FD",
              }}
            >
              РИТУАЛ НЕДЕЛИ · 20 минут · 10 задач
            </span>
            <span
              style={{
                padding: "5px 14px",
                borderRadius: 999,
                backgroundColor: "rgba(16, 185, 129, 0.18)",
                border: `1px solid ${COLORS.emerald}`,
                fontFamily: F.mono,
                fontSize: 16,
                fontWeight: 600,
                color: COLORS.emerald,
              }}
            >
              LIVE · ПОНЕДЕЛЬНИК
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <div
              style={{
                fontFamily: F.display,
                fontSize: 34,
                fontWeight: 800,
                color: channelColor ?? "#FFFFFF",
                letterSpacing: "-0.02em",
              }}
            >
              Тест понедельника
            </div>
            <div
              style={{
                fontFamily: F.mono,
                fontSize: 22,
                fontWeight: 600,
                color: "#E2E8F0",
              }}
            >
              Задача 04 / 10
            </div>
          </div>
        </div>
      </div>

      {/* Main Stage Container: Question Card (Frames 50–440) -> Leaderboard Rise (Frames 420–660) */}
      <div style={{ position: "relative", flex: 1, width: "100%" }}>
        {/* QUESTION & EXPLANATION CARD */}
        {frame >= 48 && frame < 445 && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              borderRadius: 28,
              padding: "26px 28px",
              backgroundColor: COLORS.surface,
              border: `1.5px solid ${
                dtWrong >= 0 && dtWrong < 26
                  ? COLORS.coral
                  : dtRight >= 0
                  ? COLORS.emerald
                  : COLORS.surfaceBorder
              }`,
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              boxShadow: "0 24px 64px rgba(0, 0, 0, 0.45)",
              opacity: questionEnter * (1 - leaderboardPhase),
              transform: `translateX(${cardShakeX}px) translateY(${
                (1 - questionEnter) * 40 - leaderboardPhase * 50
              }px) scale(${0.95 + questionEnter * 0.05})`,
            }}
          >
            {/* Problem Statement */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 14,
              }}
            >
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 18,
                  color: "#94A3B8",
                }}
              >
                ЛОГАРИФМИЧЕСКОЕ УРАВНЕНИЕ · ОРТ / ЕГЭ
              </span>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 18,
                  color: COLORS.indigo,
                  fontWeight: 600,
                }}
              >
                +100 XP
              </span>
            </div>

            <div
              style={{
                padding: "20px 24px",
                borderRadius: 20,
                backgroundColor: "rgba(15, 23, 42, 0.78)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                marginBottom: 22,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span
                style={{
                  fontFamily: F.body,
                  fontSize: 26,
                  fontWeight: 700,
                  color: "#F8FAFC",
                }}
              >
                Найдите корень:
              </span>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 32,
                  fontWeight: 600,
                  color: "#FFFFFF",
                  letterSpacing: "0.02em",
                }}
              >
                log₂(x + 1) = 3
              </span>
            </div>

            {/* 2x2 Answer Option Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 16,
              }}
            >
              {OPTIONS.map((opt) => {
                const isWrongTapped = opt.id === "Б" && dtWrong >= 0;
                const isRightTapped = opt.id === "А" && dtRight >= 0;

                const wrongFlash =
                  opt.id === "Б" && dtWrong >= 0
                    ? interpolate(dtWrong, [0, 35], [1, 0.35], {
                        extrapolateLeft: "clamp",
                        extrapolateRight: "clamp",
                      })
                    : 0;

                return (
                  <div
                    key={opt.id}
                    style={{
                      position: "relative",
                      overflow: "hidden",
                      borderRadius: 20,
                      padding: "20px 22px",
                      backgroundColor: isWrongTapped
                        ? `rgba(244, 63, 94, ${0.22 + wrongFlash * 0.38})`
                        : "rgba(15, 23, 42, 0.72)",
                      border: `2px solid ${
                        isRightTapped
                          ? COLORS.emerald
                          : isWrongTapped
                          ? COLORS.coral
                          : "rgba(255, 255, 255, 0.12)"
                      }`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    {/* Emerald Sweep Fill on Correct Option (А) */}
                    {isRightTapped && (
                      <div
                        style={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          bottom: 0,
                          width: `${emeraldSweep * 100}%`,
                          background: `linear-gradient(90deg, ${COLORS.emerald}66, ${COLORS.emerald}33)`,
                          zIndex: 0,
                        }}
                      />
                    )}

                    <div
                      style={{
                        position: "relative",
                        zIndex: 1,
                        display: "flex",
                        alignItems: "center",
                        gap: 14,
                      }}
                    >
                      <div
                        style={{
                          width: 38,
                          height: 38,
                          borderRadius: 12,
                          backgroundColor: isRightTapped
                            ? COLORS.emerald
                            : isWrongTapped
                            ? COLORS.coral
                            : "rgba(255, 255, 255, 0.1)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontFamily: F.display,
                          fontSize: 20,
                          fontWeight: 800,
                          color: "#FFFFFF",
                        }}
                      >
                        {opt.id}
                      </div>
                      <span
                        style={{
                          fontFamily: F.mono,
                          fontSize: 26,
                          fontWeight: 600,
                          color: "#F8FAFC",
                        }}
                      >
                        {opt.label}
                      </span>
                    </div>

                    {/* Self-drawing SVG Checkmark on Correct Option (А) */}
                    {isRightTapped && (
                      <svg
                        width={34}
                        height={34}
                        viewBox="0 0 34 34"
                        style={{
                          position: "relative",
                          zIndex: 1,
                          transform: `scale(${xpBounce})`,
                        }}
                      >
                        <circle cx={17} cy={17} r={16} fill={COLORS.emerald} />
                        <path
                          d="M10 17.5 L15 22.5 L24.5 12"
                          fill="none"
                          stroke="#FFFFFF"
                          strokeWidth={3.2}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeDasharray={24}
                          strokeDashoffset={24 * (1 - checkmarkDraw)}
                        />
                      </svg>
                    )}

                    {/* Coral Error Cross on Option (Б) */}
                    {isWrongTapped && (
                      <span
                        style={{
                          position: "relative",
                          zIndex: 1,
                          fontFamily: F.mono,
                          fontSize: 20,
                          fontWeight: 700,
                          color: COLORS.coral,
                        }}
                      >
                        ОШИБКА
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Step-by-Step Explanation Accordion (Expands Smoothly with SPRINGS.soft after Wrong Attempt) */}
            {frame >= 128 && (
              <div
                style={{
                  marginTop: 18,
                  maxHeight: 220 * accordionExpand,
                  opacity: accordionExpand,
                  overflow: "hidden",
                  borderRadius: 20,
                  backgroundColor: "rgba(30, 58, 138, 0.28)",
                  border: "1px solid rgba(99, 102, 241, 0.45)",
                  padding: "18px 22px",
                }}
              >
                <div
                  style={{
                    fontFamily: F.mono,
                    fontSize: 17,
                    fontWeight: 600,
                    color: "#93C5FD",
                    marginBottom: 8,
                    letterSpacing: "0.06em",
                  }}
                >
                  ПОШАГОВЫЙ РАЗБОР · ПРАВИЛО ЛОГАРИФМА
                </div>
                <div
                  style={{
                    fontFamily: F.mono,
                    fontSize: 22,
                    color: "#F8FAFC",
                    lineHeight: 1.45,
                  }}
                >
                  1) log₂(x + 1) = 3 ⇒ x + 1 = 2³ = 8
                  <br />
                  2) Вычитаем 1: <span style={{ color: COLORS.emerald, fontWeight: 700 }}>x = 8 − 1 = 7 (Ответ А)</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* +100 XP Upward Floater + 14 Gravity-Simulated Radial Particles on Win */}
        {dtRight >= 0 && dtRight <= 115 && (
          <svg
            width={870}
            height={600}
            viewBox="0 0 870 600"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              pointerEvents: "none",
              overflow: "visible",
              zIndex: 50,
            }}
          >
            {/* 14 Radial Particles with Simulated Gravity */}
            {particles.map((p, i) => {
              const t = dtRight * 0.55;
              const gravity = 0.26;
              const px = 220 + p.vx * t;
              const py = 220 + p.vy * t + 0.5 * gravity * t * t;
              const pOpacity = interpolate(dtRight, [0, 75], [1, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <circle
                  key={i}
                  cx={px}
                  cy={py}
                  r={p.size}
                  fill={p.color}
                  opacity={pOpacity}
                />
              );
            })}

            {/* +100 XP Badge Launching Upward with SPRINGS.bounce */}
            <g
              transform={`translate(220, ${
                200 - interpolate(dtRight, [0, 75], [0, 125], { extrapolateRight: "clamp" })
              }) scale(${xpBounce})`}
              opacity={interpolate(dtRight, [55, 95], [1, 0], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              })}
            >
              <rect
                x={-88}
                y={-28}
                width={176}
                height={56}
                rx={28}
                fill={COLORS.emerald}
                stroke="#FFFFFF"
                strokeWidth={2.5}
              />
              <text
                x={0}
                y={8}
                textAnchor="middle"
                fill="#FFFFFF"
                style={{
                  fontFamily: F.display,
                  fontSize: 25,
                  fontWeight: 800,
                }}
              >
                +100 XP
              </text>
            </g>
          </svg>
        )}

        {/* PHASE 3: LEADERBOARD RISE (Local 420–660 | Global 720–960) */}
        {frame >= 415 && (
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              borderRadius: 28,
              padding: "24px 26px",
              backgroundColor: COLORS.surface,
              border: `1.5px solid ${COLORS.surfaceBorder}`,
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              boxShadow: "0 24px 64px rgba(0, 0, 0, 0.5)",
              opacity: leaderboardPhase,
              transform: `translateY(${(1 - leaderboardPhase) * 45}px)`,
            }}
          >
            {/* Scope Tabs: Страна · Область · Школа */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 20,
              }}
            >
              <div style={{ display: "flex", gap: 10 }}>
                {["Страна", "Область", "Школа"].map((tab, idx) => (
                  <div
                    key={tab}
                    style={{
                      padding: "8px 18px",
                      borderRadius: 999,
                      backgroundColor:
                        idx === 0 ? COLORS.brandBlueBright : "rgba(255, 255, 255, 0.06)",
                      border: `1px solid ${
                        idx === 0 ? COLORS.indigo : COLORS.surfaceBorder
                      }`,
                      fontFamily: F.body,
                      fontSize: 19,
                      fontWeight: 700,
                      color: "#FFFFFF",
                    }}
                  >
                    {tab}
                  </div>
                ))}
              </div>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 18,
                  color: COLORS.emerald,
                  fontWeight: 600,
                }}
              >
                РЕЙТИНГ НЕДЕЛИ
              </span>
            </div>

            {/* Leaderboard Rows container (height 4 * 88 = 352px) */}
            <div style={{ position: "relative", height: 356 }}>
              {COMPETITORS.map((comp, idx) => {
                // Stagger in at 3-frame intervals using SPRINGS.snap
                const rowEnter = spring({
                  frame: frame - (425 + idx * 3),
                  fps,
                  config: SPRINGS.snap,
                });

                // As student climbs past each competitor, that competitor shifts down 1 slot (88px)
                const threshold = (2 - idx) / 3;
                const shiftDown = interpolate(
                  climbProgress,
                  [threshold, threshold + 0.32],
                  [0, 1],
                  {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                    easing: Easing.out(Easing.cubic),
                  }
                );

                const rowTop = (idx + shiftDown) * 88;
                const displayedRank = idx + 1 + (shiftDown > 0.5 ? 1 : 0);

                return (
                  <div
                    key={comp.name}
                    style={{
                      position: "absolute",
                      left: 0,
                      right: 0,
                      top: rowTop,
                      height: 76,
                      borderRadius: 18,
                      padding: "0 22px",
                      backgroundColor: "rgba(15, 23, 42, 0.72)",
                      border: `1px solid ${COLORS.surfaceBorder}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      opacity: rowEnter,
                      transform: `scale(${0.92 + rowEnter * 0.08})`,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                      <div
                        style={{
                          width: 44,
                          height: 44,
                          borderRadius: 12,
                          backgroundColor: "rgba(255, 255, 255, 0.08)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontFamily: F.mono,
                          fontSize: 20,
                          fontWeight: 700,
                          color: "#CBD5E1",
                        }}
                      >
                        #{displayedRank}
                      </div>
                      <div>
                        <div
                          style={{
                            fontFamily: F.body,
                            fontSize: 22,
                            fontWeight: 700,
                            color: "#F8FAFC",
                          }}
                        >
                          {comp.name}
                        </div>
                        <div
                          style={{
                            fontFamily: F.body,
                            fontSize: 16,
                            color: "#94A3B8",
                          }}
                        >
                          {comp.school}
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        fontFamily: F.mono,
                        fontSize: 21,
                        fontWeight: 600,
                        color: "#E2E8F0",
                      }}
                    >
                      {comp.xp}
                    </div>
                  </div>
                );
              })}

              {/* Student Row Sliding Upward Past All 3 Competitors to #1 */}
              {(() => {
                const studentEnter = spring({
                  frame: frame - (425 + 3 * 3),
                  fps,
                  config: SPRINGS.snap,
                });
                const studentTop = (1 - climbProgress) * 3 * 88;
                return (
                  <div
                    style={{
                      position: "absolute",
                      left: 0,
                      right: 0,
                      top: studentTop,
                      height: 78,
                      borderRadius: 18,
                      padding: "0 22px",
                      background: `linear-gradient(135deg, ${COLORS.brandBlueBright}, ${COLORS.indigo})`,
                      border: `2px solid ${COLORS.emerald}`,
                      boxShadow: "0 16px 38px rgba(99, 102, 241, 0.48)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      opacity: studentEnter,
                      transform: `scale(${0.92 + studentEnter * 0.08 + climbProgress * 0.03})`,
                      zIndex: 10,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                      <div
                        style={{
                          width: 48,
                          height: 48,
                          borderRadius: 14,
                          backgroundColor: COLORS.emerald,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontFamily: F.display,
                          fontSize: 22,
                          fontWeight: 800,
                          color: "#FFFFFF",
                        }}
                      >
                        #{studentRank}
                      </div>
                      <div>
                        <div
                          style={{
                            fontFamily: F.body,
                            fontSize: 23,
                            fontWeight: 800,
                            color: "#FFFFFF",
                          }}
                        >
                          Ты (Тима) · Серия 6 недель
                        </div>
                        <div
                          style={{
                            fontFamily: F.mono,
                            fontSize: 16,
                            color: "#E0E7FF",
                          }}
                        >
                          Чуйская область · 10/10 верно
                        </div>
                      </div>
                    </div>
                    <div
                      style={{
                        fontFamily: F.mono,
                        fontSize: 24,
                        fontWeight: 700,
                        color: "#FFFFFF",
                      }}
                    >
                      {studentXP} XP
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Kinetic Russian Caption */}
      <KineticCaption
        kicker="ЕЖЕНЕДЕЛЬНЫЙ СОРЕВНОВАТЕЛЬНЫЙ РЕЖИМ"
        text="Тест понедельника: держи темп каждую неделю"
        startFrame={10}
        endFrame={648}
        accentColor={COLORS.emerald}
      />
    </SafeZone>
  );

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* RGB Chromatic Aberration Channels on Entry (Frames 0–5 / Global 300–305) */}
      {rgbShift > 0.1 && (
        <>
          <AbsoluteFill
            style={{
              transform: `translateX(${-rgbShift}px)`,
              opacity: 0.45,
              mixBlendMode: "screen",
              filter: "hue-rotate(-40deg) saturate(220%)",
            }}
          >
            {renderSceneContent(COLORS.coral)}
          </AbsoluteFill>
          <AbsoluteFill
            style={{
              transform: `translateX(${rgbShift}px)`,
              opacity: 0.45,
              mixBlendMode: "screen",
              filter: "hue-rotate(40deg) saturate(220%)",
            }}
          >
            {renderSceneContent(COLORS.brandBlueBright)}
          </AbsoluteFill>
        </>
      )}

      {/* Primary Crisp Channel */}
      {renderSceneContent()}

      {/* High-Energy Entry Flash Overlay */}
      {entryFlashOpacity > 0.01 && (
        <AbsoluteFill
          style={{
            background: `radial-gradient(circle at 50% 50%, #FFFFFF, ${COLORS.indigo} 60%, transparent 100%)`,
            opacity: entryFlashOpacity,
            pointerEvents: "none",
          }}
        />
      )}

      {/* Sleek Touch Indicator for Wrong Tap (Б) and Correct Retry (А) */}
      <TouchIndicator
        waypoints={touchWaypoints}
        tapFrames={[wrongTapFrame, rightTapFrame]}
        visibleRange={[70, 320]}
        accentColor={dtRight >= -6 ? COLORS.emerald : COLORS.coral}
      />
    </AbsoluteFill>
  );
};
