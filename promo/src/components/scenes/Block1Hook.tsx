import React, { useMemo } from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, F, HEIGHT, SPRINGS, WIDTH } from "../../theme";
import { KineticCaption } from "../shared/KineticCaption";
import { SafeZone } from "../shared/SafeZone";
import { TouchIndicator, TouchWaypoint } from "../shared/TouchIndicator";

interface Point {
  x: number;
  y: number;
}

interface LetterSpec {
  char: string;
  points: Point[];
  extraSegments?: [Point, Point][];
}

const FLOATING_SYMBOLS = [
  { sym: "π", x: 130, y: 340, size: 54, speed: 0.025, phase: 0.4, color: COLORS.indigo },
  { sym: "√2", x: 780, y: 370, size: 46, speed: 0.02, phase: 1.2, color: COLORS.brandBlueBright },
  { sym: "∑", x: 165, y: 1080, size: 62, speed: 0.022, phase: 2.3, color: COLORS.emerald },
  { sym: "log₂x", x: 720, y: 1120, size: 42, speed: 0.018, phase: 3.1, color: COLORS.indigo },
  { sym: "∫f(x)dx", x: 220, y: 540, size: 38, speed: 0.019, phase: 4.0, color: "#94A3B8" },
  { sym: "Δ = b²−4ac", x: 640, y: 550, size: 36, speed: 0.021, phase: 5.2, color: COLORS.brandBlueBright },
  { sym: "sin²α + cos²α = 1", x: 460, y: 1040, size: 34, speed: 0.017, phase: 2.8, color: "#94A3B8" },
];

export const Block1Hook: React.FC = () => {
  const frame = useCurrentFrame(); // 0..300
  const { fps } = useVideoConfig();

  // Define M-O-N-D-A-Y on a crisp dot-matrix coordinate lattice inside the SafeZone
  // Center of letter "O" is at (320, 770)
  const letters: LetterSpec[] = useMemo(() => {
    const yTop = 690;
    const yMid = 770;
    const yBot = 850;
    return [
      {
        char: "M",
        points: [
          { x: 96, y: yBot },
          { x: 96, y: yTop },
          { x: 148, y: yMid },
          { x: 200, y: yTop },
          { x: 200, y: yBot },
        ],
      },
      {
        char: "O",
        points: [
          { x: 256, y: yTop },
          { x: 364, y: yTop },
          { x: 364, y: yBot },
          { x: 256, y: yBot },
          { x: 256, y: yTop },
        ],
      },
      {
        char: "N",
        points: [
          { x: 416, y: yBot },
          { x: 416, y: yTop },
          { x: 512, y: yBot },
          { x: 512, y: yTop },
        ],
      },
      {
        char: "D",
        points: [
          { x: 564, y: yTop },
          { x: 642, y: yTop + 26 },
          { x: 656, y: yMid },
          { x: 642, y: yBot - 26 },
          { x: 564, y: yBot },
          { x: 564, y: yTop },
        ],
      },
      {
        char: "A",
        points: [
          { x: 696, y: yBot },
          { x: 744, y: yTop },
          { x: 792, y: yBot },
          { x: 774, y: yMid + 18 },
          { x: 714, y: yMid + 18 },
        ],
      },
      {
        char: "Y",
        points: [
          { x: 828, y: yTop },
          { x: 868, y: yMid },
          { x: 908, y: yTop },
          { x: 868, y: yMid },
          { x: 868, y: yBot },
        ],
      },
    ];
  }, []);

  // Build ordered segments (~6 frames per segment) starting at frame 12
  const { segments, nodes, touchWaypoints, tapFrames } = useMemo(() => {
    const segList: {
      from: Point;
      to: Point;
      startFrame: number;
      endFrame: number;
      length: number;
      letterIndex: number;
    }[] = [];
    const nodeList: { point: Point; connectFrame: number; letterIndex: number }[] = [];
    const waypoints: TouchWaypoint[] = [];
    const taps: number[] = [];

    let cursorFrame = 12;
    const framesPerSegment = 6;

    letters.forEach((letter, li) => {
      const pts = letter.points;
      nodeList.push({ point: pts[0], connectFrame: cursorFrame, letterIndex: li });
      waypoints.push({ frame: cursorFrame, x: pts[0].x, y: pts[0].y });
      taps.push(cursorFrame);

      for (let i = 0; i < pts.length - 1; i++) {
        const p1 = pts[i];
        const p2 = pts[i + 1];
        const len = Math.hypot(p2.x - p1.x, p2.y - p1.y);
        const startF = cursorFrame;
        const endF = cursorFrame + framesPerSegment;
        segList.push({
          from: p1,
          to: p2,
          startFrame: startF,
          endFrame: endF,
          length: len,
          letterIndex: li,
        });
        cursorFrame = endF;
        nodeList.push({ point: p2, connectFrame: cursorFrame, letterIndex: li });
        waypoints.push({ frame: cursorFrame, x: p2.x, y: p2.y });
      }
      taps.push(cursorFrame);
      cursorFrame += 4; // brief pause between letters
    });

    return {
      segments: segList,
      nodes: nodeList,
      touchWaypoints: waypoints,
      tapFrames: taps,
    };
  }, [letters]);

  // Center of letter "O" is at (310, 770)
  const oCenter = { x: 310, y: 770 };

  // Transition Out (Frames 260–300): Camera zooms directly through the center dot of the letter "O"
  const zoomOutProgress = interpolate(frame, [260, 300], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  const cameraScale = 1 + Math.pow(zoomOutProgress, 2.6) * 42;
  const cameraTranslateX = (WIDTH / 2 - oCenter.x) * zoomOutProgress;
  const cameraTranslateY = (HEIGHT / 2 - oCenter.y) * zoomOutProgress;

  // Compute current active drawing head for the glowing particle trail (last N = 14 positions)
  const trailCount = 14;
  const activeHeadSamples = useMemo(() => {
    const getPointAtFrame = (f: number): Point | null => {
      if (f < 12 || f > 215) return null;
      for (const seg of segments) {
        if (f >= seg.startFrame && f <= seg.endFrame) {
          const p = interpolate(f, [seg.startFrame, seg.endFrame], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.cubic),
          });
          return {
            x: seg.from.x + (seg.to.x - seg.from.x) * p,
            y: seg.from.y + (seg.to.y - seg.from.y) * p,
          };
        }
      }
      // Between letters, hold at most recent segment end
      for (let i = segments.length - 1; i >= 0; i--) {
        if (f >= segments[i].endFrame) {
          return segments[i].to;
        }
      }
      return null;
    };

    return Array.from({ length: trailCount }, (_, idx) => {
      const sampleF = frame - idx * 0.9;
      const pt = getPointAtFrame(sampleF);
      return {
        pt,
        ageFactor: (trailCount - idx) / trailCount,
      };
    });
  }, [frame, segments]);

  const cardEnter = spring({
    frame: frame - 4,
    fps,
    config: SPRINGS.snap,
  });

  const oCenterBounce = spring({
    frame: frame - 68,
    fps,
    config: SPRINGS.bounce,
  });

  const oPortalRadius =
    8 * oCenterBounce + Math.pow(zoomOutProgress, 2.1) * 1650;

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Camera rig zooming through the center dot of "O" on frames 260–300 */}
      <AbsoluteFill
        style={{
          transformOrigin: `${oCenter.x}px ${oCenter.y}px`,
          transform: `translate(${cameraTranslateX}px, ${cameraTranslateY}px) scale(${cameraScale})`,
        }}
      >
        {/* Floating Math Symbols Drifting Subtly in Background */}
        {FLOATING_SYMBOLS.map((item, idx) => {
          const driftY = Math.sin(frame * item.speed + item.phase) * 18;
          const driftX = Math.cos(frame * item.speed * 0.8 + item.phase) * 12;
          const symEnter = spring({
            frame: frame - idx * 5,
            fps,
            config: SPRINGS.soft,
          });
          return (
            <div
              key={idx}
              style={{
                position: "absolute",
                left: item.x + driftX,
                top: item.y + driftY,
                fontFamily: F.mono,
                fontSize: item.size,
                fontWeight: 600,
                color: item.color,
                opacity: symEnter * 0.24,
                textShadow: `0 0 24px ${item.color}`,
                pointerEvents: "none",
              }}
            >
              {item.sym}
            </div>
          );
        })}

        {/* Hero Dot-Matrix Interactive Stage Card (1 backdrop-filter blur panel) */}
        <div
          style={{
            position: "absolute",
            left: 54,
            top: 590,
            width: 896,
            height: 360,
            borderRadius: 36,
            backgroundColor: COLORS.surface,
            border: `1.5px solid ${COLORS.surfaceBorder}`,
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            boxShadow:
              "0 28px 80px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.14)",
            opacity: cardEnter,
            transform: `scale(${0.92 + cardEnter * 0.08})`,
          }}
        >
          {/* Top bar metadata inside the matrix card */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "22px 32px 0 32px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  backgroundColor: COLORS.emerald,
                  boxShadow: `0 0 12px ${COLORS.emerald}`,
                }}
              />
              <span
                style={{
                  fontFamily: F.mono,
                  fontSize: 18,
                  color: "#CBD5E1",
                  letterSpacing: "0.08em",
                }}
              >
                MONDAY.KG · ИНТЕРАКТИВНАЯ МАТРИЦА
              </span>
            </div>
            <span
              style={{
                fontFamily: F.mono,
                fontSize: 18,
                color: COLORS.indigo,
                fontWeight: 600,
              }}
            >
              60 FPS · DOT-ENGINE
            </span>
          </div>
        </div>

        {/* SVG Dot-Matrix Polylines, Particle Trail, and Node Bounce Flares */}
        <svg
          width={WIDTH}
          height={HEIGHT}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          style={{ position: "absolute", inset: 0, overflow: "visible" }}
        >
          <defs>
            <linearGradient id="mondayStrokeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={COLORS.brandBlueBright} />
              <stop offset="55%" stopColor={COLORS.indigo} />
              <stop offset="100%" stopColor={COLORS.emerald} />
            </linearGradient>
            <filter id="neonGlow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Inactive reference lattice dots behind the letters */}
          {nodes.map((n, i) => (
            <circle
              key={`ghost-${i}`}
              cx={n.point.x}
              cy={n.point.y}
              r={4.5}
              fill="rgba(255, 255, 255, 0.16)"
            />
          ))}

          {/* Polyline Segments Drawn over ~6 Frames Each with Easing.out(Easing.cubic) */}
          {segments.map((seg, i) => {
            if (frame < seg.startFrame) return null;
            const drawProgress = interpolate(
              frame,
              [seg.startFrame, seg.endFrame],
              [0, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.out(Easing.cubic),
              }
            );
            const dashOffset = seg.length * (1 - drawProgress);

            return (
              <g key={`seg-${i}`}>
                {/* Outer glow stroke */}
                <line
                  x1={seg.from.x}
                  y1={seg.from.y}
                  x2={seg.to.x}
                  y2={seg.to.y}
                  stroke={COLORS.indigo}
                  strokeWidth={16}
                  strokeLinecap="round"
                  strokeDasharray={seg.length}
                  strokeDashoffset={dashOffset}
                  opacity={0.32}
                />
                {/* Crisp core polyline segment */}
                <line
                  x1={seg.from.x}
                  y1={seg.from.y}
                  x2={seg.to.x}
                  y2={seg.to.y}
                  stroke="url(#mondayStrokeGrad)"
                  strokeWidth={8.5}
                  strokeLinecap="round"
                  strokeDasharray={seg.length}
                  strokeDashoffset={dashOffset}
                />
              </g>
            );
          })}

          {/* Particle Trail: Last N path positions with decaying opacity & scale */}
          {activeHeadSamples.map((sample, idx) => {
            if (!sample.pt) return null;
            return (
              <circle
                key={`trail-pt-${idx}`}
                cx={sample.pt.x}
                cy={sample.pt.y}
                r={14 * sample.ageFactor}
                fill={idx === 0 ? "#FFFFFF" : COLORS.indigo}
                opacity={sample.ageFactor * 0.85}
              />
            );
          })}

          {/* Connected Grid Dots with SPRINGS.bounce Scale Pulse + Blue/Indigo Glow */}
          {nodes.map((node, i) => {
            if (frame < node.connectFrame) return null;
            const pulse = spring({
              frame: frame - node.connectFrame,
              fps,
              config: SPRINGS.bounce,
            });
            const flareDecay = interpolate(
              frame - node.connectFrame,
              [0, 26],
              [1, 0],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }
            );

            return (
              <g key={`node-${i}`}>
                {/* Expanding flare ring on connection */}
                {flareDecay > 0.02 && (
                  <circle
                    cx={node.point.x}
                    cy={node.point.y}
                    r={8 + (1 - flareDecay) * 28}
                    fill="none"
                    stroke={COLORS.indigo}
                    strokeWidth={2.5 * flareDecay}
                    opacity={flareDecay * 0.85}
                  />
                )}
                {/* Glowing halo */}
                <circle
                  cx={node.point.x}
                  cy={node.point.y}
                  r={12 * pulse}
                  fill={COLORS.brandBlueBright}
                  opacity={0.42}
                />
                {/* Connected dot core */}
                <circle
                  cx={node.point.x}
                  cy={node.point.y}
                  r={6.2 * pulse}
                  fill="#FFFFFF"
                  stroke={COLORS.indigo}
                  strokeWidth={2.5}
                />
              </g>
            );
          })}

          {/* Center Dot of the Letter "O" — Portal Target for Transition Out (260–300) */}
          {frame >= 68 && (
            <g>
              <circle
                cx={oCenter.x}
                cy={oCenter.y}
                r={18 * oCenterBounce + Math.sin(frame * 0.15) * 3}
                fill="none"
                stroke={COLORS.indigo}
                strokeWidth={2}
                opacity={0.7 * (1 - zoomOutProgress)}
              />
              <circle
                cx={oCenter.x}
                cy={oCenter.y}
                r={Math.max(0, oPortalRadius)}
                fill={zoomOutProgress > 0.15 ? COLORS.brandBlue : COLORS.indigo}
              />
              <circle
                cx={oCenter.x}
                cy={oCenter.y}
                r={Math.max(0, 5 * oCenterBounce * (1 - zoomOutProgress))}
                fill="#FFFFFF"
              />
            </g>
          )}
        </svg>
      </AbsoluteFill>

      {/* SafeZone Overlay for Top Header Badge & Bottom Kinetic Russian Caption */}
      <SafeZone
        style={{
          opacity: interpolate(frame, [260, 286], [1, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {/* Top Hero Pill */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 12,
              padding: "12px 22px",
              borderRadius: 999,
              backgroundColor: "rgba(30, 58, 138, 0.45)",
              border: "1px solid rgba(99, 102, 241, 0.45)",
              boxShadow: "0 12px 30px rgba(37, 99, 235, 0.25)",
            }}
          >
            <div
              style={{
                width: 30,
                height: 30,
                borderRadius: 8,
                background: `linear-gradient(135deg, ${COLORS.brandBlueBright}, ${COLORS.brandBlue})`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontFamily: F.display,
                fontSize: 18,
                fontWeight: 800,
                color: "#FFFFFF",
              }}
            >
              M
            </div>
            <span
              style={{
                fontFamily: F.body,
                fontSize: 22,
                fontWeight: 700,
                color: "#F8FAFC",
              }}
            >
              Monday · Подготовка к математике
            </span>
          </div>
        </div>

        {/* Bottom Caption Overlay + Exam Badge Strip */}
        <KineticCaption
          kicker="ПЛАТФОРМА №1 ДЛЯ ЭКЗАМЕНОВ"
          text="Вся математика экзамена — в одном движении."
          startFrame={10}
          endFrame={282}
          showExamBadges={true}
          accentColor={COLORS.indigo}
        />
      </SafeZone>

      {/* Sleek Touch Indicator Tracing the MONDAY Dot-Matrix */}
      <TouchIndicator
        waypoints={touchWaypoints}
        tapFrames={tapFrames}
        visibleRange={[8, 236]}
        accentColor={COLORS.indigo}
      />
    </AbsoluteFill>
  );
};
