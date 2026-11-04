import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, F, SPRINGS } from "../../theme";
import { KineticCaption } from "../shared/KineticCaption";
import { SafeZone } from "../shared/SafeZone";
import { TouchIndicator, TouchWaypoint } from "../shared/TouchIndicator";

const FILTER_PILLS = [
  { label: "Сложность: Средняя", tapAt: 62 },
  { label: "Источник: ЕГЭ / ОРТ / SAT", tapAt: 70 },
  { label: "Тема: Логарифмы", tapAt: 125 },
  { label: "Сборник 2026", tapAt: 155 },
  { label: "Ошибка в прошлых", tapAt: 999 },
  { label: "Решённые: Скрыть", tapAt: 999 },
];

const BUBBLE_ROWS = [
  { qNum: "01", selectedCol: 0, tapFrame: 225 }, // А
  { qNum: "02", selectedCol: 2, tapFrame: 265 }, // В
  { qNum: "03", selectedCol: 1, tapFrame: 305 }, // Б
  { qNum: "04", selectedCol: 3, tapFrame: 345 }, // Г
];

const COL_HEADERS = ["А", "Б", "В", "Г"];

export const Block3QuestionBank: React.FC = () => {
  const frame = useCurrentFrame(); // Local 0..660 (Global 960..1620)
  const { fps } = useVideoConfig();

  // Entry Transition (Local 0–24 | Global 960–984): Fast horizontal swipe with simulated directional motion blur
  // (The ONLY motion-blur transition in the video)
  const swipeProgress = interpolate(frame, [0, 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const swipeTranslateX = (1 - swipeProgress) * 1080;
  const horizontalBlurStdDev = interpolate(frame, [0, 8, 22], [38, 24, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Filter Carousel horizontal scroll (Local 30–190 | Global 990–1150)
  const carouselScrollX = interpolate(frame, [30, 175], [0, -140], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  // Countdown timer ticking from 19:59 -> 19:58 -> 19:57
  const secondsLeft = Math.max(52, 59 - Math.floor(frame / 60));
  const timerString = `19:${secondsLeft.toString().padStart(2, "0")}`;

  // Built-in Desmos Calculator Modal for SAT (Global 1360–1620 | Local 400–660)
  const desmosEnter = spring({
    frame: frame - 400,
    fps,
    config: SPRINGS.snap,
  });

  // Constant-speed deterministic typewriter for "y = a(x - h)^2 + k"
  const fullEquation = "y = a(x - h)^2 + k";
  const typedLength = Math.floor(
    interpolate(frame, [422, 476], [0, fullEquation.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const typedEquation = fullEquation.slice(0, typedLength);

  // Parabola curve plotting progress (Local 470–585 | Global 1430–1545)
  const plotProgress = interpolate(frame, [470, 585], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  // Generate deterministic parabola SVG points in Desmos graph viewport (width 760, height 270)
  const parabolaGeometry = useMemo(() => {
    const samples = 80;
    const pts: { x: number; y: number }[] = [];
    let totalLen = 0;
    for (let i = 0; i <= samples; i++) {
      const t = i / samples; // 0..1
      const mathX = -3.2 + t * 6.4; // -3.2 .. +3.2
      // Vertex at (0.4, -1.2), opening upward: y = 0.48 * (x - 0.4)^2 - 1.2
      const mathY = 0.48 * Math.pow(mathX - 0.4, 2) - 1.2;
      const svgX = 380 + mathX * 92;
      const svgY = 175 - mathY * 58;
      if (i > 0) {
        const prev = pts[i - 1];
        totalLen += Math.hypot(svgX - prev.x, svgY - prev.y);
      }
      pts.push({ x: svgX, y: svgY });
    }
    const pathD = pts
      .map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ");
    return { pts, pathD, totalLen };
  }, []);

  const tipIndex = Math.min(
    parabolaGeometry.pts.length - 1,
    Math.max(0, Math.floor(plotProgress * (parabolaGeometry.pts.length - 1)))
  );
  const tipPoint = parabolaGeometry.pts[tipIndex];

  // Touch Indicator Waypoints across Filter Carousel -> Бланк ответов -> Desmos button
  const touchWaypoints: TouchWaypoint[] = [
    { frame: 45, x: 520, y: 380 },
    { frame: 70, x: 430, y: 365 }, // Tap Источник: ЕГЭ / ОРТ / SAT
    { frame: 125, x: 660, y: 365 }, // Tap Логарифмы
    { frame: 225, x: 495, y: 690 }, // Bubble #1 (А)
    { frame: 265, x: 635, y: 762 }, // Bubble #2 (В)
    { frame: 305, x: 565, y: 834 }, // Bubble #3 (Б)
    { frame: 345, x: 705, y: 906 }, // Bubble #4 (Г)
    { frame: 398, x: 760, y: 495 }, // Tap Desmos calculator button
  ];

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Directional Horizontal Motion Blur SVG Filter (Active only during frames 0–22) */}
      <svg width={0} height={0} style={{ position: "absolute" }}>
        <defs>
          <filter id="horizontalSwipeBlur" x="-20%" y="-10%" width="140%" height="120%">
            <feGaussianBlur
              in="SourceGraphic"
              stdDeviation={`${horizontalBlurStdDev.toFixed(1)},0`}
            />
          </filter>
        </defs>
      </svg>

      <AbsoluteFill
        style={{
          transform: `translateX(${swipeTranslateX}px)`,
          filter: horizontalBlurStdDev > 0.5 ? "url(#horizontalSwipeBlur)" : undefined,
        }}
      >
        <SafeZone justify="flex-start" style={{ gap: 18 }}>
          {/* 1. FILTER CAROUSEL (Global 990–1150 | Local 30–190) */}
          <div
            style={{
              borderRadius: 24,
              padding: "18px 22px",
              backgroundColor: COLORS.surface,
              border: `1px solid ${COLORS.surfaceBorder}`,
              overflow: "hidden",
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
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 17,
                  fontWeight: 600,
                  color: "#94A3B8",
                  letterSpacing: "0.08em",
                }}
              >
                БАНК ЗАДАЧ · 14 500+ ВОПРОСОВ И СБОРНИКОВ
              </span>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 17,
                  color: COLORS.indigo,
                  fontWeight: 600,
                }}
              >
                ФИЛЬТРЫ АКТИВНЫ
              </span>
            </div>

            <div
              style={{
                display: "flex",
                gap: 12,
                whiteSpace: "nowrap",
                transform: `translateX(${carouselScrollX}px)`,
              }}
            >
              {FILTER_PILLS.map((pill, idx) => {
                const isSelected = frame >= pill.tapAt;
                const fillSpring = spring({
                  frame: frame - pill.tapAt,
                  fps,
                  config: SPRINGS.bounce,
                });

                return (
                  <div
                    key={idx}
                    style={{
                      padding: "10px 20px",
                      borderRadius: 999,
                      backgroundColor: isSelected
                        ? COLORS.indigo
                        : "rgba(15, 23, 42, 0.78)",
                      border: `1.5px solid ${
                        isSelected ? "#A5B4FC" : COLORS.surfaceBorder
                      }`,
                      boxShadow: isSelected
                        ? `0 0 24px rgba(99, 102, 241, 0.55)`
                        : "none",
                      fontFamily: F.body,
                      fontSize: 19,
                      fontWeight: 700,
                      color: "#FFFFFF",
                      transform: `scale(${
                        isSelected ? 0.94 + fillSpring * 0.06 : 1
                      })`,
                    }}
                  >
                    {pill.label}
                  </div>
                );
              })}
            </div>
          </div>

          {/* 2. EXAM INTERFACE & OFFICIAL ORT/EGE БЛАНК ОТВЕТОВ (Global 1150–1360 | Local 190–400) */}
          <div
            style={{
              position: "relative",
              borderRadius: 28,
              padding: "24px 26px",
              backgroundColor: COLORS.surface,
              border: `1.5px solid ${COLORS.surfaceBorder}`,
              backdropFilter: "blur(16px)",
              WebkitBackdropFilter: "blur(16px)",
              boxShadow: "0 24px 60px rgba(0, 0, 0, 0.45)",
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            {/* Header Bar: ДЗ: свойства логарифмов | Timer 19:58 | Формулы | Desmos */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                paddingBottom: 14,
                borderBottom: `1px solid ${COLORS.surfaceBorder}`,
              }}
            >
              <div>
                <div
                  style={{
                    fontFamily: F.display,
                    fontSize: 23,
                    fontWeight: 800,
                    color: "#FFFFFF",
                  }}
                >
                  ДЗ: свойства логарифмов
                </div>
                <div
                  style={{
                    fontFamily: F.mono,
                    fontSize: 16,
                    color: "#94A3B8",
                    marginTop: 4,
                  }}
                >
                  Официальный формат бланка · Автопроверка
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {/* Timer Pill */}
                <div
                  style={{
                    padding: "8px 16px",
                    borderRadius: 12,
                    backgroundColor: "rgba(30, 58, 138, 0.55)",
                    border: "1px solid rgba(99, 102, 241, 0.45)",
                    fontFamily: F.mono,
                    fontSize: 21,
                    fontWeight: 700,
                    color: "#93C5FD",
                  }}
                >
                  ⏱ {timerString}
                </div>

                {/* Формулы Button */}
                <div
                  style={{
                    padding: "8px 16px",
                    borderRadius: 12,
                    backgroundColor: "rgba(255, 255, 255, 0.08)",
                    border: `1px solid ${COLORS.surfaceBorder}`,
                    fontFamily: F.body,
                    fontSize: 18,
                    fontWeight: 700,
                    color: "#E2E8F0",
                  }}
                >
                  Формулы
                </div>
              </div>
            </div>

            {/* Two-Column Exam Layout: Problem List Left + Бланк ответов Bubble Grid Right */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1.15fr",
                gap: 20,
                alignItems: "stretch",
              }}
            >
              {/* Left Mini-Problems */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                {[
                  "01. log₃(27) + log₃(9) = 5",
                  "02. lg(25) + lg(4) = 2",
                  "03. log₂(16) − log₂(2) = 3",
                  "04. 5^(log₅ 12) = 12",
                ].map((eq, i) => (
                  <div
                    key={i}
                    style={{
                      padding: "16px 18px",
                      borderRadius: 16,
                      backgroundColor: "rgba(15, 23, 42, 0.72)",
                      border: `1px solid ${
                        frame >= BUBBLE_ROWS[i].tapFrame
                          ? "rgba(16, 185, 129, 0.45)"
                          : "rgba(255, 255, 255, 0.08)"
                      }`,
                      fontFamily: F.mono,
                      fontSize: 18,
                      color: "#F8FAFC",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <span>{eq}</span>
                    {frame >= BUBBLE_ROWS[i].tapFrame && (
                      <span style={{ color: COLORS.emerald, fontWeight: 700 }}>✓</span>
                    )}
                  </div>
                ))}
              </div>

              {/* Right Official ORT/EGE Бланк ответов Bubble Matrix */}
              <div
                style={{
                  borderRadius: 20,
                  padding: "18px 22px",
                  backgroundColor: "#F8FAFC",
                  color: "#0F172A",
                  boxShadow: "inset 0 2px 6px rgba(15, 23, 42, 0.12)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderBottom: "2px solid #CBD5E1",
                    paddingBottom: 8,
                  }}
                >
                  <span
                    style={{
                      fontFamily: F.display,
                      fontSize: 18,
                      fontWeight: 800,
                      color: COLORS.brandBlue,
                    }}
                  >
                    БЛАНК ОТВЕТОВ
                  </span>
                  <div style={{ display: "flex", gap: 28, paddingRight: 10 }}>
                    {COL_HEADERS.map((col) => (
                      <span
                        key={col}
                        style={{
                          width: 38,
                          textAlign: "center",
                          fontFamily: F.mono,
                          fontSize: 18,
                          fontWeight: 700,
                          color: "#334155",
                        }}
                      >
                        {col}
                      </span>
                    ))}
                  </div>
                </div>

                {BUBBLE_ROWS.map((row, rIdx) => (
                  <div
                    key={row.qNum}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "4px 0",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: F.mono,
                        fontSize: 20,
                        fontWeight: 700,
                        color: "#1E293B",
                      }}
                    >
                      № {row.qNum}
                    </span>

                    <div style={{ display: "flex", gap: 28, paddingRight: 10 }}>
                      {COL_HEADERS.map((col, cIdx) => {
                        const isFilled =
                          cIdx === row.selectedCol && frame >= row.tapFrame;
                        const inkScale = spring({
                          frame: frame - row.tapFrame,
                          fps,
                          config: SPRINGS.bounce,
                        });

                        return (
                          <div
                            key={col}
                            style={{
                              width: 38,
                              height: 38,
                              borderRadius: "50%",
                              border: `2.5px solid ${
                                isFilled ? COLORS.brandBlue : "#64748B"
                              }`,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              position: "relative",
                            }}
                          >
                            <span
                              style={{
                                fontFamily: F.mono,
                                fontSize: 15,
                                fontWeight: 600,
                                color: "#94A3B8",
                              }}
                            >
                              {col}
                            </span>

                            {/* Dark-blue ink fill circle triggered by SPRINGS.bounce */}
                            {isFilled && (
                              <div
                                style={{
                                  position: "absolute",
                                  inset: 3,
                                  borderRadius: "50%",
                                  backgroundColor: COLORS.brandBlue,
                                  transform: `scale(${inkScale})`,
                                  boxShadow: "0 2px 8px rgba(30, 58, 138, 0.45)",
                                }}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 3. BUILT-IN DESMOS CALCULATOR MODAL FOR SAT (Global 1360–1620 | Local 400–660) */}
            {frame >= 398 && (
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: 26,
                  backgroundColor: "rgba(11, 15, 25, 0.99)",
                  border: `2px solid ${COLORS.indigo}`,
                  boxShadow: "0 30px 90px rgba(0, 0, 0, 0.85)",
                  padding: "22px 26px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 14,
                  opacity: desmosEnter,
                  transform: `scale(${0.86 + desmosEnter * 0.14})`,
                  zIndex: 30,
                }}
              >
                {/* Desmos Top Bar */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span
                      style={{
                        padding: "5px 12px",
                        borderRadius: 8,
                        backgroundColor: COLORS.emerald,
                        fontFamily: F.mono,
                        fontSize: 16,
                        fontWeight: 700,
                        color: "#0B0F19",
                      }}
                    >
                      SAT MATH · DESMOS
                    </span>
                    <span
                      style={{
                        fontFamily: F.display,
                        fontSize: 21,
                        fontWeight: 800,
                        color: "#FFFFFF",
                      }}
                    >
                      Встроенный графический калькулятор
                    </span>
                  </div>
                  <span
                    style={{
                      fontFamily: F.mono,
                      fontSize: 17,
                      color: "#94A3B8",
                    }}
                  >
                    a = 0.5 · h = 0.4 · k = −1.2
                  </span>
                </div>

                {/* Function Input Bar with Typewriter */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 18px",
                    borderRadius: 14,
                    backgroundColor: "rgba(30, 41, 59, 0.85)",
                    border: `1.5px solid ${COLORS.indigo}`,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <span
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: "50%",
                        backgroundColor: COLORS.emerald,
                        boxShadow: `0 0 12px ${COLORS.emerald}`,
                      }}
                    />
                    <span
                      style={{
                        fontFamily: F.mono,
                        fontSize: 26,
                        fontWeight: 600,
                        color: "#FFFFFF",
                      }}
                    >
                      {typedEquation}
                      <span
                        style={{
                          display: "inline-block",
                          width: 3,
                          height: 26,
                          backgroundColor: COLORS.indigo,
                          marginLeft: 4,
                          verticalAlign: "middle",
                          opacity: frame % 20 < 10 ? 1 : 0.2,
                        }}
                      />
                    </span>
                  </div>
                  <span
                    style={{
                      fontFamily: F.mono,
                      fontSize: 17,
                      color: COLORS.emerald,
                    }}
                  >
                    Вершина: (0.4, −1.2)
                  </span>
                </div>

                {/* Coordinate Plane & Smoothly Plotted Parabola with Glowing Tip Dot */}
                <div
                  style={{
                    flex: 1,
                    borderRadius: 16,
                    backgroundColor: "#070B14",
                    border: `1px solid ${COLORS.surfaceBorder}`,
                    overflow: "hidden",
                    position: "relative",
                  }}
                >
                  <svg
                    width={760}
                    height={230}
                    viewBox="0 0 760 230"
                    style={{ width: "100%", height: "100%", display: "block" }}
                  >
                    {/* Minor & Major Coordinate Grid Lines */}
                    {Array.from({ length: 15 }, (_, i) => (
                      <line
                        key={`vx-${i}`}
                        x1={i * 54}
                        y1={0}
                        x2={i * 54}
                        y2={230}
                        stroke="rgba(255, 255, 255, 0.06)"
                        strokeWidth={1}
                      />
                    ))}
                    {Array.from({ length: 7 }, (_, i) => (
                      <line
                        key={`hy-${i}`}
                        x1={0}
                        y1={i * 38}
                        x2={760}
                        y2={i * 38}
                        stroke="rgba(255, 255, 255, 0.06)"
                        strokeWidth={1}
                      />
                    ))}

                    {/* X and Y Axes */}
                    <line
                      x1={0}
                      y1={175}
                      x2={760}
                      y2={175}
                      stroke="rgba(255, 255, 255, 0.32)"
                      strokeWidth={2}
                    />
                    <line
                      x1={380}
                      y1={0}
                      x2={380}
                      y2={230}
                      stroke="rgba(255, 255, 255, 0.32)"
                      strokeWidth={2}
                    />

                    {/* Plotted Parabola Curve */}
                    {plotProgress > 0.01 && (
                      <>
                        <path
                          d={parabolaGeometry.pathD}
                          fill="none"
                          stroke={COLORS.emerald}
                          strokeWidth={10}
                          strokeLinecap="round"
                          strokeDasharray={parabolaGeometry.totalLen}
                          strokeDashoffset={
                            parabolaGeometry.totalLen * (1 - plotProgress)
                          }
                          opacity={0.28}
                        />
                        <path
                          d={parabolaGeometry.pathD}
                          fill="none"
                          stroke={COLORS.emerald}
                          strokeWidth={4.5}
                          strokeLinecap="round"
                          strokeDasharray={parabolaGeometry.totalLen}
                          strokeDashoffset={
                            parabolaGeometry.totalLen * (1 - plotProgress)
                          }
                        />
                        {/* Glowing Tracking Dot on Curve Tip */}
                        <circle
                          cx={tipPoint.x}
                          cy={tipPoint.y}
                          r={14}
                          fill={COLORS.emerald}
                          opacity={0.4}
                        />
                        <circle
                          cx={tipPoint.x}
                          cy={tipPoint.y}
                          r={6.5}
                          fill="#FFFFFF"
                          stroke={COLORS.emerald}
                          strokeWidth={3}
                        />
                      </>
                    )}
                  </svg>
                </div>
              </div>
            )}
          </div>

          {/* Bottom Kinetic Russian Caption */}
          <KineticCaption
            kicker="ОРТ · ЕГЭ · ОГЭ · ЕНТ · SAT · CSCA"
            text="Умный банк вопросов и сборники под любой экзамен"
            startFrame={18}
            endFrame={648}
            accentColor={COLORS.indigo}
          />
        </SafeZone>
      </AbsoluteFill>

      {/* Sleek Touch Indicator */}
      <TouchIndicator
        waypoints={touchWaypoints}
        tapFrames={[70, 125, 225, 265, 305, 345, 398]}
        visibleRange={[40, 415]}
        accentColor={COLORS.indigo}
      />
    </AbsoluteFill>
  );
};
