import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(price: number, currency = 'USD'): string {
  if (price === 0) return 'Free';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(price);
}

export function formatNumber(num: number): string {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
}

export function formatDate(date: string | Date): string {
  const d = new Date(date);
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function formatRelativeTime(date: string | Date): string {
  const now = new Date();
  const d = new Date(date);
  const diff = now.getTime() - d.getTime();
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 30) return formatDate(date);
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return 'Just now';
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

export function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    CODING: 'Coding',
    DESIGN: 'Design',
    RESEARCH: 'Research',
    WRITING: 'Writing',
    DATA_ANALYSIS: 'Data Analysis',
    AUTOMATION: 'Automation',
    COMMUNICATION: 'Communication',
    MEDIA: 'Media',
    SYSTEM: 'System',
    PRODUCTIVITY: 'Productivity',
    MONITORING: 'Monitoring',
    OTHER: 'Other',
  };
  return labels[category] || category;
}

export function getCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    CODING: '💻',
    DESIGN: '🎨',
    RESEARCH: '🔍',
    WRITING: '✍️',
    DATA_ANALYSIS: '📊',
    AUTOMATION: '⚡',
    COMMUNICATION: '💬',
    MEDIA: '🎬',
    SYSTEM: '🖥️',
    PRODUCTIVITY: '🚀',
    MONITORING: '📡',
    OTHER: '📦',
  };
  return icons[category] || '📦';
}
