import React, { useEffect } from "react";
import { AbsoluteFill, Sequence } from "remotion";
import { loadFonts } from "./fonts";
import { SceneCountdown } from "./scenes/SceneCountdown";
import { SceneStrip } from "./scenes/SceneStrip";
import { SceneMondayTest } from "./scenes/SceneMondayTest";
import { SceneSolve } from "./scenes/SceneSolve";
import { SceneRanking } from "./scenes/SceneRanking";
import { SceneOutro } from "./scenes/SceneOutro";

export interface MondayPromoProps {
  studentName?: string;
  exam?: string;
  mondaysLeft?: number;
  region?: string;
  goalScore?: number;
  ctaUrl?: string;
}

export const MondayPromo: React.FC<MondayPromoProps> = ({
  studentName = "Тима",
  exam = "ОРТ",
  mondaysLeft = 21,
  region = "Чуйская область",
  goalScore = 190,
  ctaUrl = "monday.kg",
}) => {
  useEffect(() => {
    loadFonts();
  }, []);

  return (
    <AbsoluteFill style={{ backgroundColor: "#020B29" }}>
      {/* 0:00 – 0:04 (0 to 240 frames): Scene 1 — Countdown Hook */}
      <Sequence from={0} durationInFrames={240}>
        <SceneCountdown mondays={mondaysLeft} name={studentName} />
      </Sequence>

      {/* 0:04 – 0:08 (240 to 480 frames): Scene 2 — Monday Strip Timeline & Iris */}
      <Sequence from={240} durationInFrames={240}>
        <SceneStrip />
      </Sequence>

      {/* 0:08 – 0:13 (480 to 780 frames): Scene 3 — Monday Test Live Arena */}
      <Sequence from={480} durationInFrames={300}>
        <SceneMondayTest name={studentName} exam={exam} />
      </Sequence>

      {/* 0:13 – 0:20 (780 to 1200 frames): Scene 4 — Solve, Instant Feedback & Grid */}
      <Sequence from={780} durationInFrames={420}>
        <SceneSolve />
      </Sequence>

      {/* 0:20 – 0:26 (1200 to 1560 frames): Scene 5 — Weekly Leaderboard Podium & Climb */}
      <Sequence from={1200} durationInFrames={360}>
        <SceneRanking region={region} />
      </Sequence>

      {/* 0:26 – 0:30 (1560 to 1800 frames): Scene 6 — Goal DotRing & Outro CTA */}
      <Sequence from={1560} durationInFrames={240}>
        <SceneOutro goalScore={goalScore} ctaUrl={ctaUrl} />
      </Sequence>
    </AbsoluteFill>
  );
};
