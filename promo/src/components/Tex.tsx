import React, { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

/* KaTeX, like the app (monday/static/vendor/katex). */
export const Tex: React.FC<{ tex: string; style?: React.CSSProperties; display?: boolean }> = ({ tex, style, display }) => {
  const html = useMemo(() => katex.renderToString(tex, { throwOnError: false, displayMode: !!display }), [tex, display]);
  return <span style={style} dangerouslySetInnerHTML={{ __html: html }} />;
};
