import { staticFile } from "remotion";

const FACES: [string, string, number][] = [
  ["Onest", "onest-cyrillic-400-normal.woff2", 400],
  ["Onest", "onest-latin-400-normal.woff2", 400],
  ["Onest", "onest-cyrillic-600-normal.woff2", 600],
  ["Onest", "onest-latin-600-normal.woff2", 600],
  ["Onest", "onest-cyrillic-700-normal.woff2", 700],
  ["Onest", "onest-latin-700-normal.woff2", 700],
  ["Onest", "onest-cyrillic-800-normal.woff2", 800],
  ["Onest", "onest-latin-800-normal.woff2", 800],
  ["Unbounded", "unbounded-cyrillic-800-normal.woff2", 800],
  ["Unbounded", "unbounded-latin-800-normal.woff2", 800],
  ["IBM Plex Mono", "ibm-plex-mono-cyrillic-600-normal.woff2", 600],
  ["IBM Plex Mono", "ibm-plex-mono-latin-600-normal.woff2", 600],
];

let injected = false;

export const loadFonts = () => {
  if (injected || typeof document === "undefined") return;
  injected = true;

  const style = document.createElement("style");
  style.id = "monday-fonts";
  style.textContent = FACES.map(
    ([family, file, weight]) => `
    @font-face {
      font-family: '${family}';
      font-weight: ${weight};
      font-style: normal;
      src: url('${staticFile(`fonts/${file}`)}') format('woff2');
      font-display: swap;
    }
  `,
  ).join("\n");

  document.head.appendChild(style);
};
