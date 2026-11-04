import React from "react";
import { SAFE_ZONE } from "../../theme";

export interface SafeZoneProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  justify?: React.CSSProperties["justifyContent"];
  align?: React.CSSProperties["alignItems"];
}

/**
 * Master TikTok / Reels / Shorts 9:16 SafeZone wrapper.
 * Enforces paddingTop: 250px, paddingBottom: 400px, paddingRight: 150px, paddingLeft: 60px
 * so all text overlays and key UI focal points are never covered by platform icons.
 */
export const SafeZone: React.FC<SafeZoneProps> = ({
  children,
  style,
  justify = "space-between",
  align = "stretch",
}) => {
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        paddingTop: SAFE_ZONE.paddingTop,
        paddingBottom: SAFE_ZONE.paddingBottom,
        paddingRight: SAFE_ZONE.paddingRight,
        paddingLeft: SAFE_ZONE.paddingLeft,
        boxSizing: "border-box",
        display: "flex",
        flexDirection: "column",
        justifyContent: justify,
        alignItems: align,
        pointerEvents: "none",
        ...style,
      }}
    >
      {children}
    </div>
  );
};
