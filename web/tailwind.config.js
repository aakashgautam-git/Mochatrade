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
        // Derived in semantic.css. Use these, never an opacity modifier:
        // Tailwind drops bg-pos/10 silently on var() colours.
        "pos-fg": "var(--pos-fg)",
        "neg-fg": "var(--neg-fg)",
        "warn-fg": "var(--warn-fg)",
        "halt-fg": "var(--halt-fg)",
        "accent-fg": "var(--accent-fg)",
        "pos-soft": "var(--pos-soft)",
        "neg-soft": "var(--neg-soft)",
        "warn-soft": "var(--warn-soft)",
        "halt-soft": "var(--halt-soft)",
        "pos-edge": "var(--pos-edge)",
        "neg-edge": "var(--neg-edge)",
        "warn-edge": "var(--warn-edge)",
        "halt-edge": "var(--halt-edge)",
        "accent-edge": "var(--accent-edge)",
        "halt-solid": "var(--halt-solid)",
        "on-halt-solid": "var(--on-halt-solid)",
        "accent-solid": "var(--accent-solid)",
        "on-accent-solid": "var(--on-accent-solid)",
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
