import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#000000',
          secondary: '#0a0a0a',
          tertiary: '#111111',
          elevated: '#1a1a1a',
          hover: '#222222',
          active: '#2a2a2a',
        },
        border: {
          primary: '#222222',
          secondary: '#333333',
          focus: '#555555',
          active: '#444444',
        },
        text: {
          primary: '#ffffff',
          secondary: '#a0a0a0',
          tertiary: '#666666',
          inverse: '#000000',
        },
        accent: {
          DEFAULT: '#e86520',
          hover: '#cc5518',
          muted: 'rgba(232, 101, 32, 0.15)',
          light: '#f08535',
          subtle: 'rgba(232, 101, 32, 0.08)',
          border: 'rgba(232, 101, 32, 0.25)',
        },
        success: '#22c55e',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#3b82f6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'pulse-gentle': 'pulseGentle 2s infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        pulseGentle: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
