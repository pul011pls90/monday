import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, HEIGHT, SPRINGS, WIDTH } from "../../theme";

export interface DotGridBackgroundProps {
  /** Global timeline frame (0..3600) */
  globalFrame?: number;
}

const COLS = 17;
const ROWS = 31;
const SPACING = 60;
const OFFSET_X = (WIDTH - (COLS - 1) * SPACING) / 2; // 60px
const OFFSET_Y = (HEIGHT - (ROWS - 1) * SPACING) / 2; // 60px

export const getGridPoint = (col: number, row: number) => ({
  x: OFFSET_X + col * SPACING,
  y: OFFSET_Y + row * SPACING,
});

export const DotGridBackground: React.FC<DotGridBackgroundProps> = ({ globalFrame }) => {
  const localFrame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const frame = globalFrame ?? localFrame;

  const dots = useMemo(() => {
    const list: { col: number; row: number; x: number; y: number; distCenter: number; angle: number }[] = [];
    const cx = WIDTH / 2;
    const cy = HEIGHT / 2;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = OFFSET_X + c * SPACING;
        const y = OFFSET_Y + r * SPACING;
        const dx = x - cx;
        const dy = y - cy;
        list.push({
          col: c,
          row: r,
          x,
          y,
          distCenter: Math.hypot(dx, dy),
          angle: Math.atan2(dy, dx),
        });
      }
    }
    return list;
  }, []);

  // Block 5 Parallax (frames 2160–3000)
  const block5Zoom =
    frame >= 2160 && frame < 3000
      ? spring({
          frame: frame - 2360,
          fps,
          config: SPRINGS.soft,
        }) -
        spring({
          frame: frame - 2940,
          fps,
          config: SPRINGS.soft,
        })
      : 0;

  const bgScale = 1 + Math.max(0, block5Zoom) * 0.45;
  const bgShiftX = Math.max(0, block5Zoom) * -45;
  const bgShiftY = Math.max(0, block5Zoom) * 35;

  // Block 6 Vacuum Funnel (frames 3000–3180) and Shockwave (3180–3280)
  const funnelProgress =
    frame >= 3000 && frame <= 3200
      ? interpolate(frame, [3000, 3180], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.in(Easing.quad),
        })
      : 0;

  const postSlamRestore =
    frame > 3180
      ? spring({
          frame: frame - 3185,
          fps,
          config: SPRINGS.soft,
        })
      : 0;

  // Ambient spotlight drifting smoothly across scenes
  const spotX = WIDTH * 0.5 + Math.sin(frame * 0.015) * 180;
  const spotY = HEIGHT * 0.44 + Math.cos(frame * 0.012) * 240;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bgDark,
        overflow: "hidden",
      }}
    >
      {/* Deep ambient radial nebulas */}
      <div
        style={{
          position: "absolute",
          inset: -200,
          background: `
            radial-gradient(680px circle at ${spotX}px ${spotY}px, rgba(37, 99, 235, 0.19), transparent 70%),
            radial-gradient(540px circle at ${WIDTH - spotX * 0.7}px ${HEIGHT * 0.72}px, rgba(99, 102, 241, 0.14), transparent 70%),
            radial-gradient(900px circle at 50% 50%, rgba(30, 58, 138, 0.22), rgba(11, 15, 25, 0.98) 75%)
          `,
          transform: `translate(${bgShiftX * 0.5}px, ${bgShiftY * 0.5}px) scale(${1 + Math.max(0, block5Zoom) * 0.2})`,
        }}
      />

      {/* Subtle architectural coordinate hairlines */}
      <svg
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${bgShiftX}px, ${bgShiftY}px) scale(${bgScale})`,
          transformOrigin: "540px 960px",
        }}
      >
        <g stroke="rgba(255, 255, 255, 0.03)" strokeWidth={1}>
          <line x1={540} y1={0} x2={540} y2={HEIGHT} />
          <line x1={0} y1={960} x2={WIDTH} y2={960} />
          <circle cx={540} cy={960} r={360} fill="none" strokeDasharray="6 10" />
          <circle cx={540} cy={960} r={600} fill="none" strokeDasharray="4 14" />
        </g>

        {/* Signature Dot Grid */}
        {dots.map((d, i) => {
          const wave = Math.sin(frame * 0.04 + d.col * 0.35 + d.row * 0.25);
          const baseOpacity = 0.16 + (wave + 1) * 0.07;
          const baseRadius = 2.2 + (wave + 1) * 0.45;

          let drawX = d.x;
          let drawY = d.y;
          let dotColor = wave > 0.65 ? COLORS.indigo : "#94A3B8";
          let opacity = baseOpacity;
          let radius = baseRadius;

          // During Block 6 Vacuum Funnel (3000–3180), grid dots spiral into (540, 960)
          if (frame >= 3000 && frame < 3260) {
            const activeFunnel = funnelProgress * (1 - postSlamRestore);
            const r = d.distCenter * (1 - activeFunnel * 0.96);
            const theta = d.angle + activeFunnel * activeFunnel * 4.2;
            drawX = 540 + Math.cos(theta) * r;
            drawY = 960 + Math.sin(theta) * r;
            if (activeFunnel > 0.1) {
              dotColor = d.col % 2 === 0 ? COLORS.indigo : COLORS.brandBlueBright;
              opacity = Math.min(0.85, baseOpacity + activeFunnel * 0.55);
              radius = baseRadius + activeFunnel * 1.6;
            }
          }

          return (
            <circle
              key={i}
              cx={drawX}
              cy={drawY}
              r={radius}
              fill={dotColor}
              opacity={opacity}
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
