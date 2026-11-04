/* Centralized Configuration & Single Source of Truth for Monday 60s Vertical Promo (9:16, 1080x1920 @ 60fps) */

export const WIDTH = 1080;
export const HEIGHT = 1920;
export const FPS = 60;
export const DURATION_IN_FRAMES = 3600; // 60 seconds @ 60fps

// Legacy square size alias for backward compatibility with older scenes
export const SIZE = 1080;

export const COLORS = {
  bgDark: "#0B0F19", // deep space navy-black
  brandBlue: "#1E3A8A", // deep Monday blue
  brandBlueBright: "#2563EB", // primary Monday blue from UI
  indigo: "#6366F1", // electric indigo accent
  emerald: "#10B981", // correct answer / mastery state
  coral: "#F43F5E", // error / weak spot badge
  amber: "#F59E0B", // streak / highlight accent
  cyan: "#06B6D4", // science / Darwin accent
  surface: "rgba(255, 255, 255, 0.06)",
  surfaceElevated: "rgba(255, 255, 255, 0.09)",
  surfaceBorder: "rgba(255, 255, 255, 0.12)",
  textPrimary: "#F8FAFC",
  textSecondary: "#94A3B8",
  textMuted: "#64748B",
} as const;

export const SPRINGS = {
  // ~0% overshoot — use for panels, modals, cards entering
  snap: {
    mass: 1,
    damping: 28,
    stiffness: 200,
  },
  // ~0% overshoot — use for camera moves, text reveals, background transitions
  soft: {
    mass: 1,
    damping: 20,
    stiffness: 120,
  },
  // ~30% overshoot — use ONLY for checkmarks, +100 XP floaters, dot flares, button release
  bounce: {
    mass: 1,
    damping: 10,
    stiffness: 220,
  },
  // ~33% overshoot — use ONLY for the final Block 6 logo slam
  slam: {
    mass: 1,
    damping: 12,
    stiffness: 320,
  },
} as const;

export const SAFE_ZONE = {
  paddingTop: 250,
  paddingBottom: 400,
  paddingRight: 150,
  paddingLeft: 60,
  // Inner safe dimensions: 1080 - 60 - 150 = 870px width, 1920 - 250 - 400 = 1270px height
  innerWidth: 1080 - 60 - 150,
  innerHeight: 1920 - 250 - 400,
} as const;

export const BLOCKS = {
  block1Hook: { start: 0, end: 300, duration: 300 },
  block2MondayTest: { start: 300, end: 960, duration: 660 },
  block3QuestionBank: { start: 960, end: 1620, duration: 660 },
  block4MicroSessions: { start: 1620, end: 2160, duration: 540 },
  block5SkillMap: { start: 2160, end: 3000, duration: 840 },
  block6Outro: { start: 3000, end: 3600, duration: 600 },
} as const;

export const EXAM_BADGES = ["ОРТ", "ЕНТ", "ЕГЭ", "ОГЭ", "SAT", "CSCA"] as const;

export interface SoundCue {
  frame: number;
  type: "whoosh" | "tap" | "error_buzz" | "xp_chime" | "bass_slam" | "sparkle" | "riser";
  label: string;
  block: 1 | 2 | 3 | 4 | 5 | 6;
}

export const SOUND_CUES: SoundCue[] = [
  // Block 1: Hook + Interactive Dot-Matrix Logo (0–300)
  { frame: 10, type: "sparkle", label: "Dot-matrix polyline M-O-N-D-A-Y draw start", block: 1 },
  { frame: 48, type: "tap", label: "Letter M node lock & flare", block: 1 },
  { frame: 84, type: "tap", label: "Letter O node lock & flare", block: 1 },
  { frame: 120, type: "tap", label: "Letter N node lock & flare", block: 1 },
  { frame: 156, type: "tap", label: "Letter D node lock & flare", block: 1 },
  { frame: 192, type: "tap", label: "Letter A node lock & flare", block: 1 },
  { frame: 222, type: "xp_chime", label: "Letter Y complete — full MONDAY matrix glow", block: 1 },
  { frame: 260, type: "whoosh", label: "Camera dive through center dot of letter O", block: 1 },

  // Block 2: Тест понедельника (300–960)
  { frame: 300, type: "whoosh", label: "RGB chromatic flash entry into Тест понедельника", block: 2 },
  { frame: 355, type: "whoosh", label: "Question card snap entry", block: 2 },
  { frame: 405, type: "tap", label: "Touch tap on wrong option (Б)", block: 2 },
  { frame: 408, type: "error_buzz", label: "Coral red flash & decaying sine shake", block: 2 },
  { frame: 435, type: "whoosh", label: "Step-by-step explanation accordion expand", block: 2 },
  { frame: 555, type: "tap", label: "Touch tap on correct option (А)", block: 2 },
  { frame: 560, type: "xp_chime", label: "Emerald sweep + SVG checkmark + +100 XP burst", block: 2 },
  { frame: 725, type: "whoosh", label: "Leaderboard stagger entry", block: 2 },
  { frame: 810, type: "xp_chime", label: "Student climbs to #1 rank", block: 2 },

  // Block 3: Банк вопросов, Сборники & Desmos (960–1620)
  { frame: 960, type: "whoosh", label: "Fast horizontal motion-blur swipe transition", block: 3 },
  { frame: 1030, type: "tap", label: "Filter pill tap: Источник ЕГЭ / ОРТ / SAT", block: 3 },
  { frame: 1085, type: "tap", label: "Filter pill tap: Логарифмы", block: 3 },
  { frame: 1185, type: "tap", label: "Answer sheet bubble tap #1", block: 3 },
  { frame: 1225, type: "tap", label: "Answer sheet bubble tap #2", block: 3 },
  { frame: 1265, type: "tap", label: "Answer sheet bubble tap #3", block: 3 },
  { frame: 1305, type: "tap", label: "Answer sheet bubble tap #4", block: 3 },
  { frame: 1365, type: "whoosh", label: "SAT Desmos calculator modal snap open", block: 3 },
  { frame: 1430, type: "sparkle", label: "Parabola y = a(x - h)^2 + k plot sweep", block: 3 },

  // Block 4: Сессии на ходу — Franklin / Feynman / Darwin / Einstein (1620–2160)
  { frame: 1620, type: "whoosh", label: "Center-line split-screen vertical curtains open", block: 4 },
  { frame: 1710, type: "tap", label: "Time pill 10 мин selection", block: 4 },
  { frame: 1775, type: "tap", label: "Question slider bezier slide to 10", block: 4 },
  { frame: 1840, type: "tap", label: "Лестница difficulty toggle activate", block: 4 },
  { frame: 1915, type: "tap", label: "Preset activate: Франклин (~5 мин)", block: 4 },
  { frame: 1970, type: "tap", label: "Preset activate: Фейнман (~10 мин)", block: 4 },
  { frame: 2025, type: "tap", label: "Preset activate: Дарвин (~20 мин)", block: 4 },
  { frame: 2080, type: "xp_chime", label: "Preset activate: Эйнштейн (~30 мин)", block: 4 },

  // Block 5: Карта навыков & Видео-разборы (2160–3000)
  { frame: 2160, type: "whoosh", label: "Skill Map grid entry", block: 5 },
  { frame: 2230, type: "sparkle", label: "Sequential skill dots illumination", block: 5 },
  { frame: 2370, type: "whoosh", label: "3D Parallax 4x camera zoom to Алгебра (слабое место)", block: 5 },
  { frame: 2515, type: "tap", label: "Tap weak spot node to grow explanation modal", block: 5 },
  { frame: 2525, type: "whoosh", label: "Modal grows directly from tapped node", block: 5 },
  { frame: 2710, type: "tap", label: "YouTube video review play pulse", block: 5 },

  // Block 6: Vacuum Funnel & Brand Slam Outro (3000–3600)
  { frame: 3000, type: "riser", label: "Vacuum funnel spiral inward to singularity (540, 960)", block: 6 },
  { frame: 3180, type: "bass_slam", label: "MONDAY logomark + M icon slam & shockwave ring", block: 6 },
  { frame: 3365, type: "whoosh", label: "Closing tagline stagger reveal", block: 6 },
  { frame: 3420, type: "sparkle", label: "Exam pills & monday.kg CTA badge reveal", block: 6 },
];

export const F = {
  body: '"Onest", system-ui, -apple-system, sans-serif',
  display: '"Unbounded", "Onest", system-ui, -apple-system, sans-serif',
  mono: '"IBM Plex Mono", ui-monospace, Menlo, monospace',
};

// Legacy tokens preserved for existing 1:1 scene files
export const C = {
  powder: "#BBCFF4",
  cornflower: "#7FA3F3",
  electric: "#2B60E5",
  navy: "#153893",
  midnight: "#020B29",
  bar: "#0A1A5C",
  mhHi: "#1d2fa8",
  mhMid: "#0c1872",
  mhLo: "#070f4d",
  royal: "#2747d8",
  pale: "#8fa6ff",
  mist: "#c9d3ff",
  paper: "#f3f5ff",
  text: "#0E0E0E",
  text2: "#3D3D3D",
  muted: "#5E5E5E",
  line: "#E4E4E1",
  surface2: "#F6F6F3",
  accent: "#1F4FE0",
  accentBright: "#4C86FF",
  heroMuted: "#A9C9F2",
  btn: "#153893",
  ok: "#1E8E5A",
  okSoft: "#E7F6EE",
  bad: "#C93A3A",
  live: "#e5484d",
  gold: "#c8930d",
  silver: "#7d8597",
  bronze: "#b06a3b",
};

export const GRAD_DEEP = `linear-gradient(135deg, ${C.electric} 0%, ${C.navy} 70%, ${C.midnight} 100%)`;
export const MH_BG = `radial-gradient(120% 140% at 85% 20%, ${C.mhHi} 0%, ${C.mhMid} 45%, ${C.mhLo} 100%)`;
export const CARD_SHADOW = "0 1px 2px rgba(14,14,14,.04), 0 10px 30px rgba(26,40,90,.07)";
