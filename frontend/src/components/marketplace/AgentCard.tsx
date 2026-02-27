'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Star, Download, Shield, Monitor, Code2, Palette,
  Search, Database, FileText, Terminal, Settings, Zap, Brain
} from 'lucide-react';
import { formatPrice, truncate, getCategoryLabel } from '@/lib/utils';

interface AgentCardProps {
  agent: {
    id: string;
    name: string;
    slug: string;
    description: string;
    shortDescription?: string;
    category: string;
    price: number;
    pricingModel: string;
    rating?: number;
    reviewCount?: number;
    downloadCount?: number;
    verified?: boolean;
    thumbnailUrl?: string;
    developer?: {
      name?: string;
      displayName?: string;
      avatarUrl?: string;
    };
    stats?: {
      downloads: number;
      rating: number;
      reviewCount: number;
    };
    capabilities?: string[];
    tags?: string[];
    tier?: string;
  };
  index?: number;
}

const categoryIcons: Record<string, React.ReactNode> = {
  CODING: <Code2 size={16} />,
  DESIGN: <Palette size={16} />,
  RESEARCH: <Search size={16} />,
  DATA_ANALYSIS: <Database size={16} />,
  WRITING: <FileText size={16} />,
  AUTOMATION: <Terminal size={16} />,
  COMMUNICATION: <FileText size={16} />,
  PRODUCTIVITY: <Zap size={16} />,
  MEDIA: <Monitor size={16} />,
  MONITORING: <Monitor size={16} />,
  SYSTEM: <Settings size={16} />,
};

export function AgentCard({ agent, index = 0 }: AgentCardProps) {
  const [imageError, setImageError] = useState(false);
  const [exchangeRate, setExchangeRate] = useState(10); // default base rate

  // Fetch current exchange rate on mount
  useEffect(() => {
    import('@/lib/api').then(({ api }) => {
      api.exchange.getRate().then((r: any) => {
        const rate = r?.data?.rate ?? r?.rate ?? 10;
        setExchangeRate(rate);
      }).catch(() => {});
    });
  }, []);

  const priceLabel = () => {
    if (agent.price === 0 || agent.tier === 'F') return 'Free';
    const dynamicCredits = Math.max(1, Math.round(agent.price * exchangeRate));
    return `$${agent.price} · ${dynamicCredits} cr`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
    >
      <Link href={`/marketplace/${agent.slug}`} className="block group">
        <div className="card card-hover h-full flex flex-col">
          {/* Thumbnail */}
          <div className="relative aspect-video bg-bg-elevated overflow-hidden rounded-t-xl">
            {agent.thumbnailUrl && !imageError ? (
              <img
                src={agent.thumbnailUrl}
                alt={agent.name}
                className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                onError={() => setImageError(true)}
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-bg-secondary to-bg-tertiary">
                <div className="text-text-tertiary">
                  {categoryIcons[agent.category] || <Zap size={32} />}
                </div>
              </div>
            )}
            {/* Price badge */}
            <div className="absolute top-3 right-3">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold ${
                agent.price === 0 
                  ? 'bg-success/20 text-success border border-success/30' 
                  : 'bg-bg-primary/80 backdrop-blur-sm text-text-primary border border-border-primary'
              }`}>
                {priceLabel()}
              </span>
            </div>
            {/* Verified badge */}
            {agent.verified && (
              <div className="absolute top-3 left-3">
                <span className="px-2 py-1 rounded-lg text-xs bg-accent/20 text-accent border border-accent/30 flex items-center gap-1">
                  <Shield size={10} />
                  Verified
                </span>
              </div>
            )}
          </div>

          {/* Content */}
          <div className="p-4 flex-1 flex flex-col">
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-semibold text-text-primary group-hover:text-white transition-colors line-clamp-1">
                {agent.name}
              </h3>
              <span className="flex-shrink-0 text-xs text-text-tertiary px-2 py-0.5 rounded-md bg-bg-elevated border border-border-primary">
                {getCategoryLabel(agent.category)}
              </span>
            </div>

            <p className="text-sm text-text-secondary mb-4 line-clamp-2 flex-1">
              {agent.shortDescription || truncate(agent.description, 100)}
            </p>

            {/* Capabilities preview */}
            {agent.capabilities && agent.capabilities.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {agent.capabilities.slice(0, 3).map((cap) => (
                  <span
                    key={cap}
                    className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-tertiary border border-border-primary"
                  >
                    {cap.replace(/_/g, ' ').toLowerCase()}
                  </span>
                ))}
                {agent.capabilities.length > 3 && (
                  <span className="text-[10px] px-1.5 py-0.5 text-text-tertiary">
                    +{agent.capabilities.length - 3}
                  </span>
                )}
              </div>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-border-primary">
              <div className="flex items-center gap-3">
                {/* Rating */}
                <div className="flex items-center gap-1">
                  <Star size={12} className="text-warning fill-warning" />
                  <span className="text-xs text-text-secondary">
                    {(agent.rating ?? agent.stats?.rating ?? 0).toFixed(1)}
                  </span>
                  <span className="text-xs text-text-tertiary">
                    ({agent.reviewCount ?? agent.stats?.reviewCount ?? 0})
                  </span>
                </div>
                {/* Downloads */}
                <div className="flex items-center gap-1">
                  <Download size={12} className="text-text-tertiary" />
                  <span className="text-xs text-text-tertiary">
                    {agent.downloadCount ?? agent.stats?.downloads ?? 0}
                  </span>
                </div>
                {/* Active Learner indicator */}
                <div className="flex items-center gap-1" title="This agent learns from community interactions">
                  <Brain size={11} className="text-text-tertiary" />
                  <span className="text-[10px] text-text-tertiary">Learns</span>
                </div>
              </div>

              {/* Developer */}
              {agent.developer && (
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-4 rounded-full bg-bg-elevated flex items-center justify-center overflow-hidden">
                    {agent.developer.avatarUrl ? (
                      <img src={agent.developer.avatarUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-[8px] font-bold text-text-tertiary">
                        {(agent.developer.displayName || agent.developer.name || '?')[0].toUpperCase()}
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-text-tertiary truncate max-w-[80px]">
                    {agent.developer.displayName || agent.developer.name}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

export function AgentCardSkeleton() {
  return (
    <div className="card">
      <div className="aspect-video bg-bg-elevated rounded-t-xl animate-pulse" />
      <div className="p-4 space-y-3">
        <div className="h-5 bg-bg-elevated rounded animate-pulse w-3/4" />
        <div className="h-4 bg-bg-elevated rounded animate-pulse w-full" />
        <div className="h-4 bg-bg-elevated rounded animate-pulse w-2/3" />
        <div className="flex gap-1 pt-2">
          <div className="h-3 bg-bg-elevated rounded animate-pulse w-8" />
          <div className="h-3 bg-bg-elevated rounded animate-pulse w-12" />
        </div>
      </div>
    </div>
  );
}
