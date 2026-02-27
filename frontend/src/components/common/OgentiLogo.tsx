interface OgentiLogoProps {
  size?: number;
  showText?: boolean;
  className?: string;
  variant?: 'light' | 'dark';
}

export function OgentiLogo({ size = 32, showText = true, className = '' }: OgentiLogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <img
        src="/favicon.ico?v=corp"
        alt="Ogenti"
        width={size}
        height={size}
        style={{ borderRadius: Math.max(6, Math.round(size * 0.22)), display: 'block' }}
      />
      {showText && (
        <span
          className="font-semibold tracking-tight"
          style={{ fontSize: size * 0.5, color: '#ffffff' }}
        >
          ogenti
        </span>
      )}
    </span>
  );
}

export function OgentiIcon({ size = 20 }: { size?: number; variant?: 'light' | 'dark' }) {
  return (
    <img
      src="/favicon.ico?v=corp"
      alt="Ogenti"
      width={size}
      height={size}
      style={{ borderRadius: Math.max(4, Math.round(size * 0.22)), display: 'block' }}
    />
  );
}

