import React from "react";
import { Composition } from "remotion";
import { MainPromo } from "./MainPromo";
import { DURATION_IN_FRAMES, FPS, HEIGHT, WIDTH } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MondayPromo"
      component={MainPromo}
      durationInFrames={DURATION_IN_FRAMES}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={{
        showAudioCueOverlay: false,
      }}
    />
  );
};
