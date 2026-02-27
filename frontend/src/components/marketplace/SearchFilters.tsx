'use client';

import { Search, X, SlidersHorizontal } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
}

export function SearchBar({ value, onChange, onSubmit, placeholder = 'Search agents...' }: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '/' && !focused && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [focused]);

  return (
    <div className={`relative flex items-center transition-all ${
      focused ? 'ring-1 ring-border-active' : ''
    } bg-bg-secondary border border-border-primary rounded-xl`}>
      <button
        type="button"
        onClick={() => onSubmit?.()}
        className="absolute left-3 p-1 hover:bg-bg-elevated rounded-md transition-colors z-10"
        aria-label="Search"
      >
        <Search size={18} className="text-text-tertiary" />
      </button>
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(e) => e.key === 'Enter' && onSubmit?.()}
        placeholder={placeholder}
        className="w-full bg-transparent pl-11 pr-20 py-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
      />
      <div className="absolute right-3 flex items-center gap-2">
        {value && (
          <button
            onClick={() => onChange('')}
            className="p-1 hover:bg-bg-elevated rounded-md transition-colors"
          >
            <X size={14} className="text-text-tertiary" />
          </button>
        )}
        {!focused && !value && (
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono text-text-tertiary bg-bg-elevated rounded border border-border-primary">
            /
          </kbd>
        )}
      </div>
    </div>
  );
}

interface CategoryFilterProps {
  categories: { value: string; label: string; count?: number }[];
  selected: string;
  onChange: (value: string) => void;
}

export function CategoryFilter({ categories, selected, onChange }: CategoryFilterProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  return (
    <div className="relative flex-1 min-w-0 h-9 overflow-hidden">
      <div
        ref={scrollRef}
        className="flex gap-2 overflow-x-auto overflow-y-hidden scrollbar-none items-center h-9"
      >
        <FilterChip
          label="All"
          active={selected === ''}
          onClick={() => onChange('')}
        />
        {categories.map((cat) => (
          <FilterChip
            key={cat.value}
            label={cat.label}
            count={cat.count}
            active={selected === cat.value}
            onClick={() => onChange(cat.value)}
          />
        ))}
        {/* Spacer to prevent last chip from hiding under fade */}
        <div className="flex-shrink-0 w-16" aria-hidden />
      </div>
      {/* Fade effect for scrolled content — natural fog on right edge */}
      <div className="absolute top-0 right-0 h-full w-24 pointer-events-none" style={{ background: 'linear-gradient(to left, rgb(0 0 0 / 1) 0%, rgb(0 0 0 / 0.85) 30%, rgb(0 0 0 / 0.4) 65%, transparent 100%)' }} />
    </div>
  );
}

function FilterChip({
  label,
  active,
  count,
  onClick,
}: {
  label: string;
  active: boolean;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-shrink-0 flex items-center justify-center gap-1.5 px-3 h-9 rounded-lg text-xs font-medium transition-all ${
        active
          ? 'bg-accent text-white'
          : 'bg-bg-elevated text-text-secondary hover:text-text-primary border border-border-primary hover:border-border-secondary'
      }`}
    >
      {label}
      {count !== undefined && (
        <span className={`text-[10px] ${active ? 'text-black/60' : 'text-text-tertiary'}`}>
          {count}
        </span>
      )}
    </button>
  );
}

interface SortSelectProps {
  value: string;
  onChange: (value: string) => void;
}

export function SortSelect({ value, onChange }: SortSelectProps) {
  return (
    <div className="flex items-center gap-2 h-9">
      <SlidersHorizontal size={14} className="text-text-tertiary" />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-bg-elevated border border-border-primary rounded-lg px-3 h-9 text-xs text-text-secondary focus:outline-none focus:border-border-active appearance-none cursor-pointer pr-8"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
          backgroundPosition: 'right 0.5rem center',
          backgroundRepeat: 'no-repeat',
          backgroundSize: '1.25em 1.25em',
        }}
      >
        <option value="popular">Most Popular</option>
        <option value="rating">Highest Rated</option>
        <option value="recent">Newest</option>
        <option value="price_asc">Price: Low to High</option>
        <option value="price_desc">Price: High to Low</option>
      </select>
    </div>
  );
}

interface PricingFilterProps {
  value: string;
  onChange: (value: string) => void;
}

export function PricingFilter({ value, onChange }: PricingFilterProps) {
  const options = [
    { value: '', label: 'All Pricing' },
    { value: 'free', label: 'Free' },
    { value: 'paid', label: 'Paid' },
  ];

  return (
    <div className="flex gap-1.5 items-center h-9">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 h-9 rounded-lg text-xs font-medium transition-all flex items-center justify-center ${
            value === opt.value
              ? 'bg-accent text-white'
              : 'text-text-secondary hover:text-text-primary border border-border-primary hover:border-border-secondary bg-bg-elevated'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
