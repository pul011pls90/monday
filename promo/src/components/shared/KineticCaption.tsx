import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, EXAM_BADGES, F, SPRINGS } from "../../theme";

export interface KineticCaptionProps {
  text: string;
  startFrame?: number;
  endFrame?: number;
  showExamBadges?: boolean;
  kicker?: string;
  accentColor?: string;
  position?: "top" | "bottom";
}

/**
 * Russian kinetic caption overlay positioned cleanly inside the <SafeZone>.
 */
export const KineticCaption: React.FC<KineticCaptionProps> = ({
  text,
  startFrame = 8,
  endFrame,
  showExamBadges = false,
  kicker,
  accentColor = COLORS.indigo,
  position = "bottom",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const words = text.split(" ");
  const exitFactor =
    endFrame !== undefined
      ? interpolate(frame, [endFrame - 16, endFrame], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;

  const containerEnter = spring({
    frame: frame - startFrame,
    fps,
    config: SPRINGS.soft,
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        gap: 14,
        opacity: exitFactor,
        transform: `translateY(${(1 - containerEnter) * (position === "bottom" ? 24 : -24)}px)`,
        zIndex: 40,
      }}
    >
      {kicker && (
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 16px",
            borderRadius: 999,
            backgroundColor: "rgba(15, 23, 42, 0.78)",
            border: `1px solid ${COLORS.surfaceBorder}`,
            boxShadow: `0 0 20px ${accentColor}33`,
          }}
        >
          <span
            style={{
              width: 9,
              height: 9,
              borderRadius: "50%",
              backgroundColor: accentColor,
              boxShadow: `0 0 10px ${accentColor}`,
            }}
          />
          <span
            style={{
              fontFamily: F.mono,
              fontSize: 19,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "#E2E8F0",
            }}
          >
            {kicker}
          </span>
        </div>
      )}

      <div
        style={{
          padding: "20px 26px",
          borderRadius: 24,
          backgroundColor: "rgba(11, 15, 25, 0.84)",
          border: `1px solid ${COLORS.surfaceBorder}`,
          boxShadow: "0 18px 42px rgba(0, 0, 0, 0.45)",
          display: "flex",
          flexWrap: "wrap",
          gap: "6px 11px",
          maxWidth: 850,
        }}
      >
        {words.map((word, i) => {
          const wSpring = spring({
            frame: frame - (startFrame + i * 3),
            fps,
            config: SPRINGS.soft,
          });
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                fontFamily: F.display,
                fontSize: 34,
                fontWeight: 800,
                lineHeight: 1.18,
                letterSpacing: "-0.02em",
                color: COLORS.textPrimary,
                opacity: interpolate(wSpring, [0, 0.6], [0, 1], {
                  extrapolateRight: "clamp",
                }),
                transform: `translateY(${(1 - wSpring) * 16}px)`,
              }}
            >
              {word}
            </span>
          );
        })}
      </div>

      {showExamBadges && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            marginTop: 2,
          }}
        >
          {EXAM_BADGES.map((badge, idx) => {
            const bSpring = spring({
              frame: frame - (startFrame + 14 + idx * 4),
              fps,
              config: SPRINGS.snap,
            });
            return (
              <div
                key={badge}
                style={{
                  padding: "8px 18px",
                  borderRadius: 999,
                  background:
                    idx === 0 || idx === 2 || idx === 4
                      ? `linear-gradient(135deg, ${COLORS.brandBlueBright}44, ${COLORS.indigo}33)`
                      : COLORS.surface,
                  border: `1px solid ${
                    idx === 0 || idx === 2 || idx === 4
                      ? "rgba(99, 102, 241, 0.55)"
                      : COLORS.surfaceBorder
                  }`,
                  fontFamily: F.mono,
                  fontSize: 20,
                  fontWeight: 600,
                  color: "#F8FAFC",
                  letterSpacing: "0.06em",
                  opacity: bSpring,
                  transform: `scale(${0.8 + bSpring * 0.2})`,
                }}
              >
                {badge}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
