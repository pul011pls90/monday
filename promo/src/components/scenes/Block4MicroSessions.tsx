import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, F, HEIGHT, SPRINGS, WIDTH } from "../../theme";
import { KineticCaption } from "../shared/KineticCaption";
import { SafeZone } from "../shared/SafeZone";
import { TouchIndicator, TouchWaypoint } from "../shared/TouchIndicator";

const TIME_PILLS = ["5 мин", "10 мин", "15 мин", "30 мин"];

const SCIENTIST_MODES = [
  {
    name: "Франклин",
    duration: "~5 мин",
    desc: "короткий точный разбор слабых тем",
    activateAt: 295, // Global 1915
    hueColor: "#3B82F6", // Electric Blue
    badge: "БЛИЦ-ФОКУС",
  },
  {
    name: "Фейнман",
    duration: "~10 мин",
    desc: "объясни тему своими словами (проверка ИИ-наставником)",
    activateAt: 350, // Global 1970
    hueColor: COLORS.emerald, // Emerald
    badge: "ИИ-НАСТАВНИК",
  },
  {
    name: "Дарвин",
    duration: "~20 мин",
    desc: "расследуй свои ошибки",
    activateAt: 405, // Global 2025
    hueColor: COLORS.amber, // Amber Gold
    badge: "АНАЛИЗ ОШИБОК",
  },
  {
    name: "Эйнштейн",
    duration: "~30 мин",
    desc: "сложные задачи, два способа",
    activateAt: 460, // Global 2080
    hueColor: COLORS.indigo, // Deep Electric Indigo
    badge: "ХАРДКОР · 2 МЕТОДА",
  },
];

export const Block4MicroSessions: React.FC = () => {
  const frame = useCurrentFrame(); // Local 0..540 (Global 1620..2160)
  const { fps } = useVideoConfig();

  // Entry Transition (Local 0–30 | Global 1620–1650): Center-line split-screen curtains opening vertically through the dot grid
  const curtainOpen = interpolate(frame, [0, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });

  // Builder card entrance
  const builderEnter = spring({
    frame: frame - 14,
    fps,
    config: SPRINGS.snap,
  });

  // Question Count Slider (Global 1720–1810 | Local 100–190) along Easing.bezier(0.22, 1, 0.36, 1) with 2.5% settle overshoot
  const sliderRaw = interpolate(frame, [100, 155], [0, 1.025], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.22, 1, 0.36, 1),
  });
  const sliderSettle =
    frame > 155
      ? interpolate(frame, [155, 178], [1.025, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        })
      : sliderRaw;

  const questionCount = Math.round(4 + Math.min(1, sliderSettle) * 6); // 4 -> 10
  const sliderFillPercent = 20 + sliderSettle * 55; // 20% -> 75%

  // "Лестница (от лёгких к сложным)" difficulty toggle at Local 215 (Global 1835)
  const ladderActive = frame >= 215;
  const ladderSpring = spring({
    frame: frame - 215,
    fps,
    config: SPRINGS.snap,
  });

  // Touch Indicator Waypoints
  const touchWaypoints: TouchWaypoint[] = [
    { frame: 65, x: 260, y: 465 },
    { frame: 90, x: 365, y: 465 }, // Tap "10 мин"
    { frame: 105, x: 260, y: 575 }, // Drag slider start
    { frame: 158, x: 640, y: 575 }, // Drag slider end (ВОПРОСОВ: 10)
    { frame: 215, x: 760, y: 665 }, // Tap "Лестница (от лёгких к сложным)"
    { frame: 295, x: 280, y: 830 }, // Tap Франклин
    { frame: 350, x: 680, y: 830 }, // Tap Фейнман
    { frame: 405, x: 280, y: 1015 }, // Tap Дарвин
    { frame: 460, x: 680, y: 1015 }, // Tap Эйнштейн
  ];

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <SafeZone justify="flex-start" style={{ gap: 18 }}>
        {/* 1. CUSTOM SESSION BUILDER ("Собери свою сессию", Local 30–280 | Global 1650–1900) */}
        <div
          style={{
            borderRadius: 28,
            padding: "22px 26px",
            backgroundColor: COLORS.surface,
            border: `1.5px solid ${COLORS.surfaceBorder}`,
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            boxShadow: "0 22px 55px rgba(0, 0, 0, 0.45)",
            opacity: builderEnter,
            transform: `scale(${0.94 + builderEnter * 0.06})`,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {/* Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 16,
                  fontWeight: 600,
                  color: COLORS.indigo,
                  letterSpacing: "0.08em",
                }}
              >
                СЕССИИ · КОНСТРУКТОР ТРЕНИРОВКИ
              </span>
              <div
                style={{
                  fontFamily: F.display,
                  fontSize: 28,
                  fontWeight: 800,
                  color: "#FFFFFF",
                  marginTop: 2,
                }}
              >
                Собери свою сессию
              </div>
            </div>
            <div
              style={{
                padding: "7px 15px",
                borderRadius: 999,
                backgroundColor: "rgba(16, 185, 129, 0.16)",
                border: `1px solid ${COLORS.emerald}`,
                fontFamily: F.mono,
                fontSize: 16,
                fontWeight: 600,
                color: COLORS.emerald,
              }}
            >
              АДАПТИВНЫЙ ИИ
            </div>
          </div>

          {/* Time Pills: 5 мин | 10 мин | 15 мин | 30 мин */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 12,
            }}
          >
            {TIME_PILLS.map((t, idx) => {
              const isSelected = idx === 1 && frame >= 88;
              const isInitial = idx === 0 && frame < 88;
              const active = isSelected || isInitial;

              const pillScale =
                idx === 1 && frame >= 88
                  ? 1 +
                    interpolate(frame, [88, 102, 116], [0, 0.03, 0], {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                      easing: Easing.bezier(0.22, 1, 0.36, 1),
                    })
                  : 1;

              return (
                <div
                  key={t}
                  style={{
                    padding: "12px 0",
                    borderRadius: 16,
                    textAlign: "center",
                    backgroundColor: active
                      ? COLORS.brandBlueBright
                      : "rgba(15, 23, 42, 0.72)",
                    border: `1.5px solid ${
                      active ? "#93C5FD" : COLORS.surfaceBorder
                    }`,
                    boxShadow: active
                      ? "0 8px 24px rgba(37, 99, 235, 0.4)"
                      : "none",
                    fontFamily: F.mono,
                    fontSize: 20,
                    fontWeight: 700,
                    color: "#FFFFFF",
                    transform: `scale(${pillScale})`,
                  }}
                >
                  {t}
                </div>
              );
            })}
          </div>

          {/* Question Count Slider: ВОПРОСОВ: 10 */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              padding: "12px 18px",
              borderRadius: 18,
              backgroundColor: "rgba(15, 23, 42, 0.68)",
              border: `1px solid ${COLORS.surfaceBorder}`,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 18,
                  fontWeight: 700,
                  color: "#CBD5E1",
                }}
              >
                ВОПРОСОВ: <span style={{ color: "#FFFFFF", fontSize: 22 }}>{questionCount}</span>
              </span>
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 16,
                  color: COLORS.indigo,
                }}
              >
                Оптимально для 10 минут
              </span>
            </div>

            {/* Slider Track & Thumb with 2.5% Settle Overshoot */}
            <div
              style={{
                position: "relative",
                height: 14,
                borderRadius: 999,
                backgroundColor: "rgba(255, 255, 255, 0.1)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${sliderFillPercent}%`,
                  borderRadius: 999,
                  background: `linear-gradient(90deg, ${COLORS.brandBlueBright}, ${COLORS.indigo})`,
                }}
              />
              <div
                style={{
                  position: "absolute",
                  top: "50%",
                  left: `${sliderFillPercent}%`,
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  backgroundColor: "#FFFFFF",
                  border: `4px solid ${COLORS.indigo}`,
                  transform: "translate(-50%, -50%)",
                  boxShadow: `0 0 18px ${COLORS.indigo}`,
                }}
              />
            </div>
          </div>

          {/* Difficulty Toggle: Лестница (от лёгких к сложным) */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "14px 18px",
              borderRadius: 18,
              backgroundColor: ladderActive
                ? "rgba(99, 102, 241, 0.18)"
                : "rgba(15, 23, 42, 0.68)",
              border: `1.5px solid ${
                ladderActive ? COLORS.indigo : COLORS.surfaceBorder
              }`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 22 }}>📈</span>
              <div>
                <div
                  style={{
                    fontFamily: F.body,
                    fontSize: 20,
                    fontWeight: 700,
                    color: "#FFFFFF",
                  }}
                >
                  Лестница (от лёгких к сложным)
                </div>
                <div
                  style={{
                    fontFamily: F.body,
                    fontSize: 15,
                    color: "#94A3B8",
                  }}
                >
                  Плавный разогрев и выход на пик сложности
                </div>
              </div>
            </div>

            {/* Toggle Switch */}
            <div
              style={{
                width: 64,
                height: 36,
                borderRadius: 999,
                padding: 4,
                backgroundColor: ladderActive
                  ? COLORS.emerald
                  : "rgba(255, 255, 255, 0.16)",
                display: "flex",
                alignItems: "center",
                boxSizing: "border-box",
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  backgroundColor: "#FFFFFF",
                  transform: `translateX(${ladderSpring * 28}px)`,
                }}
              />
            </div>
          </div>
        </div>

        {/* 2. QUICK-START SCIENTIST MODE CARDS (Global 1900–2160 | Local 280–540) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 16,
          }}
        >
          {SCIENTIST_MODES.map((mode, idx) => {
            const nextActivate =
              idx < SCIENTIST_MODES.length - 1
                ? SCIENTIST_MODES[idx + 1].activateAt
                : 9999;
            const isActivated = frame >= mode.activateAt;
            const isCurrentHero =
              frame >= mode.activateAt && frame < nextActivate;

            const dt = frame - mode.activateAt;
            // Animate box-shadow glow blur from 0px -> 40px -> 24px as each mode activates
            const glowBlur = isActivated
              ? interpolate(dt, [0, 14, 34], [0, 40, 24], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                  easing: Easing.out(Easing.cubic),
                })
              : 0;

            const cardPop = spring({
              frame: dt,
              fps,
              config: SPRINGS.snap,
            });

            return (
              <div
                key={mode.name}
                style={{
                  borderRadius: 24,
                  padding: "20px 22px",
                  backgroundColor: isCurrentHero
                    ? "rgba(15, 23, 42, 0.92)"
                    : "rgba(15, 23, 42, 0.72)",
                  border: `2px solid ${
                    isActivated ? mode.hueColor : COLORS.surfaceBorder
                  }`,
                  boxShadow: isActivated
                    ? `0 12px ${glowBlur.toFixed(1)}px ${mode.hueColor}${
                        isCurrentHero ? "88" : "44"
                      }`
                    : "none",
                  transform: `scale(${
                    isActivated ? 0.96 + cardPop * 0.04 + (isCurrentHero ? 0.02 : 0) : 1
                  })`,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span
                    style={{
                      padding: "4px 10px",
                      borderRadius: 999,
                      backgroundColor: `${mode.hueColor}26`,
                      border: `1px solid ${mode.hueColor}`,
                      fontFamily: F.mono,
                      fontSize: 13,
                      fontWeight: 700,
                      color: mode.hueColor,
                    }}
                  >
                    {mode.badge}
                  </span>
                  <span
                    style={{
                      fontFamily: F.mono,
                      fontSize: 16,
                      fontWeight: 700,
                      color: "#E2E8F0",
                    }}
                  >
                    {mode.duration}
                  </span>
                </div>

                <div>
                  <div
                    style={{
                      fontFamily: F.display,
                      fontSize: 24,
                      fontWeight: 800,
                      color: "#FFFFFF",
                      marginBottom: 4,
                    }}
                  >
                    {mode.name}
                  </div>
                  <div
                    style={{
                      fontFamily: F.body,
                      fontSize: 16,
                      lineHeight: 1.32,
                      color: "#CBD5E1",
                    }}
                  >
                    {mode.desc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom Kinetic Russian Caption */}
        <KineticCaption
          kicker="ФРАНКЛИН · ФЕЙНМАН · ДАРВИН · ЭЙНШТЕЙН"
          text="Нет времени? Собери микро-сессию на ходу"
          startFrame={16}
          endFrame={528}
          accentColor={COLORS.indigo}
        />
      </SafeZone>

      {/* Center-Line Split-Screen Vertical Curtains Opening through Dot Grid (Frames 0–30) */}
      {curtainOpen < 0.999 && (
        <>
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: WIDTH,
              height: HEIGHT / 2,
              backgroundColor: COLORS.bgDark,
              borderBottom: `3px solid ${COLORS.indigo}`,
              boxShadow: `0 12px 40px ${COLORS.indigo}`,
              transform: `translateY(${-curtainOpen * (HEIGHT / 2 + 40)}px)`,
              zIndex: 80,
            }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              width: WIDTH,
              height: HEIGHT / 2,
              backgroundColor: COLORS.bgDark,
              borderTop: `3px solid ${COLORS.indigo}`,
              boxShadow: `0 -12px 40px ${COLORS.indigo}`,
              transform: `translateY(${curtainOpen * (HEIGHT / 2 + 40)}px)`,
              zIndex: 80,
            }}
          />
        </>
      )}

      {/* Sleek Touch Indicator */}
      <TouchIndicator
        waypoints={touchWaypoints}
        tapFrames={[90, 215, 295, 350, 405, 460]}
        visibleRange={[55, 495]}
        accentColor={COLORS.indigo}
      />
    </AbsoluteFill>
  );
};
