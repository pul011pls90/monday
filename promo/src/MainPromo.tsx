import React, { useEffect } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Block1Hook } from "./components/scenes/Block1Hook";
import { Block2MondayTest } from "./components/scenes/Block2MondayTest";
import { Block3QuestionBank } from "./components/scenes/Block3QuestionBank";
import { Block4MicroSessions } from "./components/scenes/Block4MicroSessions";
import { Block5SkillMap } from "./components/scenes/Block5SkillMap";
import { Block6Outro } from "./components/scenes/Block6Outro";
import { DotGridBackground } from "./components/shared/DotGridBackground";
import { loadFonts } from "./fonts";
import { BLOCKS, COLORS, SOUND_CUES } from "./theme";

export interface MainPromoProps {
  showAudioCueOverlay?: boolean;
}

export const MainPromo: React.FC<MainPromoProps> = ({
  showAudioCueOverlay = false,
}) => {
  const frame = useCurrentFrame();

  useEffect(() => {
    loadFonts();
  }, []);

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bgDark }}>
      {/* Persistent Signature Dot Grid across all 6 scenes (3600 frames) */}
      <DotGridBackground globalFrame={frame} />

      {/* BLOCK 1: Hook + Interactive Dot-Matrix Logo (0:00–0:05 | Frames 0–300 | 300 frames) */}
      <Sequence
        name="Block 1: Hook & Dot-Matrix Logo"
        from={BLOCKS.block1Hook.start}
        durationInFrames={BLOCKS.block1Hook.duration}
      >
        <Block1Hook />
      </Sequence>

      {/* BLOCK 2: Тест понедельника — Single Narrative Story (0:05–0:16 | Frames 300–960 | 660 frames) */}
      <Sequence
        name="Block 2: Тест понедельника"
        from={BLOCKS.block2MondayTest.start}
        durationInFrames={BLOCKS.block2MondayTest.duration}
      >
        <Block2MondayTest />
      </Sequence>

      {/* BLOCK 3: Банк вопросов, Сборники & Desmos (0:16–0:27 | Frames 960–1620 | 660 frames) */}
      <Sequence
        name="Block 3: Банк вопросов & Desmos"
        from={BLOCKS.block3QuestionBank.start}
        durationInFrames={BLOCKS.block3QuestionBank.duration}
      >
        <Block3QuestionBank />
      </Sequence>

      {/* BLOCK 4: Сессии на ходу — Franklin / Feynman / Darwin / Einstein (0:27–0:36 | Frames 1620–2160 | 540 frames) */}
      <Sequence
        name="Block 4: Микро-сессии на ходу"
        from={BLOCKS.block4MicroSessions.start}
        durationInFrames={BLOCKS.block4MicroSessions.duration}
      >
        <Block4MicroSessions />
      </Sequence>

      {/* BLOCK 5: Карта навыков & Видео-разборы (0:36–0:50 | Frames 2160–3000 | 840 frames) */}
      <Sequence
        name="Block 5: Карта навыков & Видео-разборы"
        from={BLOCKS.block5SkillMap.start}
        durationInFrames={BLOCKS.block5SkillMap.duration}
      >
        <Block5SkillMap />
      </Sequence>

      {/* BLOCK 6: Vacuum Funnel & Brand Slam Outro (0:50–1:00 | Frames 3000–3600 | 600 frames) */}
      <Sequence
        name="Block 6: Vacuum Funnel & Brand Slam Outro"
        from={BLOCKS.block6Outro.start}
        durationInFrames={BLOCKS.block6Outro.duration}
      >
        <Block6Outro />
      </Sequence>

      {/* Timeline Audio Cue Markers (visible in Remotion Studio timeline for effortless SFX drop-in) */}
      {SOUND_CUES.map((cue, idx) => (
        <Sequence
          key={`sfx-${idx}`}
          name={`SFX [${cue.type.toUpperCase()}] ${cue.label}`}
          from={cue.frame}
          durationInFrames={15}
          layout="none"
        >
          {showAudioCueOverlay ? (
            <div
              style={{
                position: "absolute",
                top: 40,
                right: 40,
                padding: "6px 14px",
                borderRadius: 999,
                backgroundColor: "rgba(99, 102, 241, 0.85)",
                color: "#FFF",
                fontSize: 14,
                fontFamily: "monospace",
                zIndex: 999,
              }}
            >
              🔊 {cue.type}: {cue.label} (f:{cue.frame})
            </div>
          ) : null}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
