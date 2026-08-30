import type { Config } from 'tailwindcss';

const config: Config = {
  // Was previously just './app/**/*' — Nav.tsx and ui.tsx live in
  // components/, so Tailwind's JIT scanner never saw classes used only
  // there (e.g. md:w-56 on the sidebar). Those classes were silently
  // absent from the compiled CSS: no build error, no console warning,
  // just the browser falling back to each element's default box behavior
  // — which is exactly what produced the squashed-to-the-right layout.
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
