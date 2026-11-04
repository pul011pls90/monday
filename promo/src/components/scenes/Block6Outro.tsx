import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, EXAM_BADGES, F, HEIGHT, SPRINGS, WIDTH } from "../../theme";
import { SafeZone } from "../shared/SafeZone";

export const Block6Outro: React.FC = () => {
  const frame = useCurrentFrame(); // Local 0..600 (Global 3000..3600)
  const { fps } = useVideoConfig();

  // 1. Vacuum Funnel (Global 3000–3180 | Local 0–180)
  // UI card fragments break into 120 signature grid dots spiraling inward to (540, 960)
  // with quadratic acceleration (angle increasing as radius decays to 0)
  const funnelT = interpolate(frame, [0, 180], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.in(Easing.quad),
  });

  const spiralDots = useMemo(() => {
    const list: {
      r0: number;
      theta0: number;
      size: number;
      color: string;
      turns: number;
    }[] = [];
    const total = 120;
    for (let i = 0; i < total; i++) {
      const ring = Math.floor(i / 15); // 0..7
      const r0 = 140 + ring * 78 + ((i * 37) % 45);
      const theta0 = ((i % 15) / 15) * Math.PI * 2 + ring * 0.42;
      const color =
        i % 3 === 0
          ? COLORS.indigo
          : i % 3 === 1
          ? COLORS.brandBlueBright
          : COLORS.emerald;
      list.push({
        r0,
        theta0,
        size: 5 + (i % 4) * 2.2,
        color,
        turns: 2.8 + (i % 5) * 0.55,
      });
    }
    return list;
  }, []);

  // 2. Logo Slam (Global 3180–3360 | Local 180–360)
  // Slams from scale(0) to scale(1) using SPRINGS.slam ({ damping: 12, stiffness: 320 })
  const slamFrame = 180;
  const dtSlam = frame - slamFrame;

  const logoSlamScale =
    dtSlam >= 0
      ? spring({
          frame: dtSlam,
          fps,
          config: SPRINGS.slam,
        })
      : 0;

  // 4-frame camera impact shake right at Local 180..184 (Global 3180..3184)
  let shakeX = 0;
  let shakeY = 0;
  if (dtSlam >= 0 && dtSlam <= 4) {
    const offsets: [number, number][] = [
      [14, -12],
      [-12, 10],
      [8, -6],
      [-4, 3],
      [0, 0],
    ];
    const pair = offsets[Math.min(4, Math.floor(dtSlam))];
    shakeX = pair[0];
    shakeY = pair[1];
  }

  // Expanding Radial Shockwave Ring triggered at Local 180
  const shockwaveProgress = interpolate(dtSlam, [0, 48], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const shockwave2Progress = interpolate(dtSlam, [6, 58], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  // 3. CTA & Badges (Global 3360–3600 | Local 360–600)
  // Stagger in at 6-frame intervals with SPRINGS.soft
  const ctaBaseFrame = 360;

  const taglineSpring = spring({
    frame: frame - ctaBaseFrame,
    fps,
    config: SPRINGS.soft,
  });

  const domainBadgeSpring = spring({
    frame: frame - (ctaBaseFrame + 6 * (EXAM_BADGES.length + 1)),
    fps,
    config: SPRINGS.soft,
  });

  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        transform: `translate(${shakeX}px, ${shakeY}px)`,
      }}
    >
      {/* SVG Layer for Vacuum Funnel Spiral & Expanding Shockwave Rings */}
      <svg
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
      >
        <defs>
          <radialGradient id="singularityCore" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#FFFFFF" stopOpacity="1" />
            <stop offset="35%" stopColor={COLORS.indigo} stopOpacity="0.85" />
            <stop offset="100%" stopColor={COLORS.brandBlue} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Vacuum Funnel Phase (Local 0..182) */}
        {frame < 184 && (
          <g>
            {/* Ghost UI card wireframes fragmenting into dots in early frames 0..45 */}
            {frame < 50 && (
              <g
                opacity={interpolate(frame, [0, 45], [0.55, 0], {
                  extrapolateRight: "clamp",
                })}
                stroke={COLORS.indigo}
                strokeWidth={2}
                fill="none"
              >
                <rect
                  x={120 + funnelT * 300}
                  y={360 + funnelT * 450}
                  width={840 * (1 - funnelT)}
                  height={240 * (1 - funnelT)}
                  rx={24}
                  strokeDasharray="12 10"
                />
                <rect
                  x={160 + funnelT * 280}
                  y={740 + funnelT * 180}
                  width={760 * (1 - funnelT)}
                  height={320 * (1 - funnelT)}
                  rx={24}
                  strokeDasharray="10 14"
                />
              </g>
            )}

            {/* Spiraling Grid Dots along Polar Trajectories Toward (540, 960) */}
            {spiralDots.map((d, i) => {
              // Quadratic radius decay: radius -> 0 as funnelT -> 1
              const currentRadius = d.r0 * (1 - funnelT * funnelT);
              // Angle increases quadratically as radius decays
              const currentAngle = d.theta0 + funnelT * funnelT * d.turns * Math.PI * 2;
              const x = 540 + Math.cos(currentAngle) * currentRadius;
              const y = 960 + Math.sin(currentAngle) * currentRadius;

              // Short polar motion tail
              const tailAngle = currentAngle - 0.18 * funnelT;
              const tailRadius = currentRadius + 24 * funnelT;
              const tx = 540 + Math.cos(tailAngle) * tailRadius;
              const ty = 960 + Math.sin(tailAngle) * tailRadius;

              return (
                <g key={i}>
                  <line
                    x1={x}
                    y1={y}
                    x2={tx}
                    y2={ty}
                    stroke={d.color}
                    strokeWidth={d.size * 0.65}
                    strokeLinecap="round"
                    opacity={0.45}
                  />
                  <circle
                    cx={x}
                    cy={y}
                    r={d.size * (1 - funnelT * 0.45)}
                    fill={d.color}
                  />
                </g>
              );
            })}

            {/* Growing Singularity Core at (540, 960) */}
            <circle
              cx={540}
              cy={960}
              r={16 + funnelT * 88}
              fill="url(#singularityCore)"
              opacity={0.35 + funnelT * 0.65}
            />
          </g>
        )}

        {/* Expanding Radial Shockwave Rings on Logo Slam (Local 180+) */}
        {dtSlam >= 0 && dtSlam <= 62 && (
          <g>
            <circle
              cx={540}
              cy={760}
              r={40 + shockwaveProgress * 780}
              fill="none"
              stroke={COLORS.indigo}
              strokeWidth={14 * (1 - shockwaveProgress)}
              opacity={(1 - shockwaveProgress) * 0.9}
            />
            {dtSlam >= 6 && (
              <circle
                cx={540}
                cy={760}
                r={30 + shockwave2Progress * 620}
                fill="none"
                stroke="#FFFFFF"
                strokeWidth={5 * (1 - shockwave2Progress)}
                opacity={(1 - shockwave2Progress) * 0.7}
              />
            )}
          </g>
        )}
      </svg>

      {/* SafeZone Container for Brand Slam, Closing Tagline, Exam Pills, and monday.kg CTA */}
      <SafeZone justify="center" align="center" style={{ gap: 36 }}>
        {/* MONDAY Logomark + "M" Icon Slamming from scale(0) to scale(1) */}
        {dtSlam >= 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 24,
              transform: `scale(${logoSlamScale})`,
            }}
          >
            {/* Signature Monday "M" Icon Tile */}
            <div
              style={{
                width: 176,
                height: 176,
                borderRadius: 42,
                background: `linear-gradient(135deg, ${COLORS.brandBlueBright} 0%, ${COLORS.brandBlue} 65%, #091336 100%)`,
                border: "3px solid rgba(255, 255, 255, 0.28)",
                boxShadow:
                  "0 28px 90px rgba(37, 99, 235, 0.65), 0 0 60px rgba(99, 102, 241, 0.55)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg width={116} height={116} viewBox="0 0 64 64">
                <path
                  d="M12 48V16h9.5l10.5 17 10.5-17H52v32h-9V30.5L32 47 21 30.5V48z"
                  fill="#FFFFFF"
                />
              </svg>
            </div>

            {/* "MONDAY" Wordmark */}
            <div
              style={{
                fontFamily: F.display,
                fontSize: 82,
                fontWeight: 800,
                letterSpacing: "-0.03em",
                color: "#FFFFFF",
                textShadow: "0 12px 45px rgba(99, 102, 241, 0.55)",
              }}
            >
              MONDAY
            </div>
          </div>
        )}

        {/* Staggered Closing Tagline, Exam Pills, and monday.kg Badge (Local 360–600 | Global 3360–3600) */}
        {frame >= ctaBaseFrame && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 26,
              textAlign: "center",
            }}
          >
            {/* Russian Closing Tagline */}
            <div
              style={{
                fontFamily: F.display,
                fontSize: 36,
                fontWeight: 800,
                lineHeight: 1.24,
                color: "#F8FAFC",
                maxWidth: 780,
                opacity: taglineSpring,
                transform: `translateY(${(1 - taglineSpring) * 28}px)`,
              }}
            >
              Вся математика экзамена — в одном движении
            </div>

            {/* Exam Pills Staggered at 6-Frame Intervals with SPRINGS.soft */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                justifyContent: "center",
                gap: 12,
              }}
            >
              {EXAM_BADGES.map((badge, idx) => {
                const pillSpring = spring({
                  frame: frame - (ctaBaseFrame + (idx + 1) * 6),
                  fps,
                  config: SPRINGS.soft,
                });
                return (
                  <div
                    key={badge}
                    style={{
                      padding: "10px 22px",
                      borderRadius: 999,
                      backgroundColor: "rgba(30, 58, 138, 0.45)",
                      border: "1.5px solid rgba(99, 102, 241, 0.55)",
                      fontFamily: F.mono,
                      fontSize: 22,
                      fontWeight: 700,
                      color: "#FFFFFF",
                      letterSpacing: "0.06em",
                      opacity: pillSpring,
                      transform: `translateY(${(1 - pillSpring) * 20}px) scale(${
                        0.88 + pillSpring * 0.12
                      })`,
                    }}
                  >
                    {badge}
                  </div>
                );
              })}
            </div>

            {/* Web / Platform CTA Badge: monday.kg */}
            <div
              style={{
                marginTop: 8,
                padding: "18px 46px",
                borderRadius: 999,
                background: `linear-gradient(135deg, ${COLORS.brandBlueBright} 0%, ${COLORS.indigo} 60%, ${COLORS.emerald} 100%)`,
                border: "2px solid #FFFFFF",
                boxShadow: "0 20px 60px rgba(99, 102, 241, 0.65)",
                display: "inline-flex",
                alignItems: "center",
                gap: 16,
                opacity: domainBadgeSpring,
                transform: `translateY(${(1 - domainBadgeSpring) * 24}px) scale(${
                  0.9 + domainBadgeSpring * 0.1
                })`,
              }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  backgroundColor: "#FFFFFF",
                  boxShadow: "0 0 14px #FFFFFF",
                }}
              />
              <span
                style={{
                  fontFamily: F.display,
                  fontSize: 38,
                  fontWeight: 800,
                  color: "#FFFFFF",
                  letterSpacing: "0.02em",
                }}
              >
                monday.kg
              </span>
            </div>
          </div>
        )}
      </SafeZone>
    </AbsoluteFill>
  );
};
