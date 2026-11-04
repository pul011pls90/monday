import React from "react";
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, HEIGHT, SPRINGS, WIDTH } from "../../theme";

export interface TouchWaypoint {
  frame: number;
  x: number;
  y: number;
}

export interface TouchIndicatorProps {
  waypoints: TouchWaypoint[];
  tapFrames?: number[];
  visibleRange?: [number, number];
  accentColor?: string;
}

const getInterpolatedPosition = (frame: number, waypoints: TouchWaypoint[]) => {
  if (waypoints.length === 0) return { x: WIDTH / 2, y: HEIGHT / 2 };
  if (frame <= waypoints[0].frame) return { x: waypoints[0].x, y: waypoints[0].y };
  if (frame >= waypoints[waypoints.length - 1].frame) {
    const last = waypoints[waypoints.length - 1];
    return { x: last.x, y: last.y };
  }

  for (let i = 0; i < waypoints.length - 1; i++) {
    const curr = waypoints[i];
    const next = waypoints[i + 1];
    if (frame >= curr.frame && frame <= next.frame) {
      const progress = interpolate(frame, [curr.frame, next.frame], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.bezier(0.22, 1, 0.36, 1),
      });
      return {
        x: curr.x + (next.x - curr.x) * progress,
        y: curr.y + (next.y - curr.y) * progress,
      };
    }
  }
  return { x: waypoints[0].x, y: waypoints[0].y };
};

/**
 * Sleek glowing mobile finger-dot with expanding tap ripples and swipe trails.
 * Never uses a desktop mouse cursor (strictly 9:16 vertical touch semantics).
 */
export const TouchIndicator: React.FC<TouchIndicatorProps> = ({
  waypoints,
  tapFrames = [],
  visibleRange,
  accentColor = COLORS.indigo,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (waypoints.length === 0) return null;

  const startFrame = visibleRange ? visibleRange[0] : waypoints[0].frame - 12;
  const endFrame = visibleRange ? visibleRange[1] : waypoints[waypoints.length - 1].frame + 28;

  if (frame < startFrame || frame > endFrame) return null;

  const entryOpacity = interpolate(frame, [startFrame, startFrame + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exitOpacity = interpolate(frame, [endFrame - 12, endFrame], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const masterOpacity = entryOpacity * exitOpacity;

  const pos = getInterpolatedPosition(frame, waypoints);

  // Compute swipe trail points from recent frames
  const trailSteps = 7;
  const trailPoints = Array.from({ length: trailSteps }, (_, idx) => {
    const age = (idx + 1) * 1.6;
    const p = getInterpolatedPosition(frame - age, waypoints);
    return {
      ...p,
      age,
      opacity: ((trailSteps - idx) / trailSteps) * 0.38,
      scale: ((trailSteps - idx) / trailSteps) * 0.78,
    };
  });

  // Compute active tap compression & release bounce
  let tapScale = 1;
  for (const tf of tapFrames) {
    const dt = frame - tf;
    if (dt >= -4 && dt <= 24) {
      if (dt < 2) {
        tapScale = interpolate(dt, [-4, 2], [1, 0.72], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
      } else {
        const release = spring({
          frame: dt - 2,
          fps,
          config: SPRINGS.bounce,
        });
        tapScale = 0.72 + release * 0.28;
      }
    }
  }

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        zIndex: 90,
        opacity: masterOpacity,
      }}
    >
      <defs>
        <radialGradient id="touchCoreGrad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.98" />
          <stop offset="45%" stopColor={accentColor} stopOpacity="0.9" />
          <stop offset="100%" stopColor={COLORS.brandBlueBright} stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Swipe Trail */}
      {trailPoints.map((tp, i) => {
        const dist = Math.hypot(tp.x - pos.x, tp.y - pos.y);
        if (dist < 4) return null;
        return (
          <circle
            key={`trail-${i}`}
            cx={tp.x}
            cy={tp.y}
            r={16 * tp.scale}
            fill={accentColor}
            opacity={tp.opacity}
          />
        );
      })}

      {/* Expanding Tap Ripples */}
      {tapFrames.map((tf, i) => {
        const dt = frame - tf;
        if (dt < 0 || dt > 34) return null;
        const tapPos = getInterpolatedPosition(tf, waypoints);
        const rippleProgress = interpolate(dt, [0, 34], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });
        const ripple2Progress = interpolate(dt, [5, 34], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });

        return (
          <g key={`ripple-${i}`}>
            <circle
              cx={tapPos.x}
              cy={tapPos.y}
              r={18 + rippleProgress * 68}
              fill="none"
              stroke={accentColor}
              strokeWidth={3.5 * (1 - rippleProgress)}
              opacity={(1 - rippleProgress) * 0.9}
            />
            {dt >= 5 && (
              <circle
                cx={tapPos.x}
                cy={tapPos.y}
                r={14 + ripple2Progress * 46}
                fill="none"
                stroke="#FFFFFF"
                strokeWidth={2 * (1 - ripple2Progress)}
                opacity={(1 - ripple2Progress) * 0.65}
              />
            )}
          </g>
        );
      })}

      {/* Outer Finger Halo */}
      <g transform={`translate(${pos.x}, ${pos.y}) scale(${tapScale})`}>
        <circle
          cx={0}
          cy={0}
          r={34}
          fill="url(#touchCoreGrad)"
          opacity={0.55}
        />
        <circle
          cx={0}
          cy={0}
          r={22}
          fill="rgba(255, 255, 255, 0.18)"
          stroke="rgba(255, 255, 255, 0.85)"
          strokeWidth={2.5}
        />
        <circle cx={0} cy={0} r={9} fill="#FFFFFF" />
      </g>
    </svg>
  );
};
