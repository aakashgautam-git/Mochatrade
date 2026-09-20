/** @type {import('tailwindcss').Config} */
// Tokens are defined once in src/styles/tokens.css and wired in here. Never put
// a raw colour value in this file or in a component.
//
// Theming is done with CSS variables, not Tailwind's dark: variant: the default
// :root is the dark war-room palette, and [data-theme="light"] swaps the token
// values for the Report and Playbook pages. Components stay theme-agnostic.
//
// Spacing uses Tailwind's stock scale, which is already a 4px grid. House rule:
// use even steps only, so the layout lands on 8px (p-2 = 8, p-4 = 16,
// p-6 = 24, p-8 = 32).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        line: "var(--line)",
        text: "var(--text)",
        "text-dim": "var(--text-dim)",
        "text-faint": "var(--text-faint)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        pos: "var(--pos)",
        neg: "var(--neg)",
        warn: "var(--warn)",
        halt: "var(--halt)",
      },
      borderColor: {
        DEFAULT: "var(--line)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
      borderRadius: {
        card: "10px",
        control: "8px",
        chip: "6px",
      },
      transitionDuration: {
        fast: "150ms",
        base: "200ms",
      },
      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.22, 0.61, 0.36, 1)",
      },
    },
  },
  plugins: [],
};
