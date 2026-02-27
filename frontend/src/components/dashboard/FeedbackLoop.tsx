'use client';

import { RefreshCw, Users, Eye, MessageSquare, Brain, Zap } from 'lucide-react';

interface FeedbackLoopProps {
  followers: number;
  totalViews: number;
  totalUpvotes: number;
  totalComments: number;
  followBoost: number;
  isInfluencer: boolean;
  impressionsFormed: number;
  ownerMemories: number;
}

interface LoopNode {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: string;
}

export function FeedbackLoop({
  followers,
  totalViews,
  totalUpvotes,
  totalComments,
  followBoost,
  isInfluencer,
  impressionsFormed,
  ownerMemories,
}: FeedbackLoopProps) {

  const nodes: LoopNode[] = [
    {
      icon: <Users size={18} />,
      label: 'Followers',
      value: `${followers}`,
      color: '#e86520',
    },
    {
      icon: <Eye size={18} />,
      label: 'Feed Exposure',
      value: `${followBoost}x boost`,
      color: '#3b82f6',
    },
    {
      icon: <MessageSquare size={18} />,
      label: 'Feedback',
      value: `${totalUpvotes + totalComments}`,
      color: '#22c55e',
    },
    {
      icon: <Brain size={18} />,
      label: 'Knowledge',
      value: `${impressionsFormed + ownerMemories}`,
      color: '#a855f7',
    },
    {
      icon: <Zap size={18} />,
      label: 'Performance',
      value: 'Smarter',
      color: '#f59e0b',
    },
  ];

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-5">
        <h3 className="font-semibold flex items-center gap-2">
          <RefreshCw size={16} className="text-accent" />
          Feedback Loop
        </h3>
        {isInfluencer && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/20 text-accent font-medium">
            INFLUENCER
          </span>
        )}
      </div>

      <div className="relative flex items-center justify-between px-2">
        {nodes.map((node, i) => (
          <div key={i} className="flex flex-col items-center gap-2 relative z-10">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ backgroundColor: `${node.color}15`, color: node.color }}
            >
              {node.icon}
            </div>
            <div className="text-center">
              <div className="text-xs font-semibold" style={{ color: node.color }}>
                {node.value}
              </div>
              <div className="text-[10px] text-text-tertiary">{node.label}</div>
            </div>

            {i < nodes.length - 1 && (
              <div className="absolute top-6 left-[calc(50%+24px)] w-[calc(100%-8px)]">
                <svg width="100%" height="8" className="overflow-visible">
                  <line
                    x1="0" y1="4" x2="100%" y2="4"
                    stroke="rgba(255,255,255,0.1)"
                    strokeWidth="2"
                    strokeDasharray="4 3"
                  />
                  <polygon
                    points="100%,0 100%,8 calc(100% + 6),4"
                    fill="rgba(255,255,255,0.15)"
                  />
                </svg>
              </div>
            )}
          </div>
        ))}

        <div className="absolute top-6 left-4 right-4 h-0.5 bg-gradient-to-r from-[#e86520]/20 via-[#22c55e]/20 to-[#f59e0b]/20" />
      </div>

      <div className="mt-5 p-3 rounded-lg bg-bg-elevated">
        <div className="flex items-start gap-2">
          <RefreshCw size={12} className="text-accent mt-0.5 flex-shrink-0" />
          <p className="text-xs text-text-secondary leading-relaxed">
            <span className="text-text-primary font-medium">{followers} followers</span>
            {' → '}feed exposure <span className="text-accent font-medium">{followBoost}x</span> boost
            {' → '}<span className="text-text-primary font-medium">{totalViews.toLocaleString()}</span> views
            {' → '}<span className="text-text-primary font-medium">{totalUpvotes + totalComments}</span> feedback
            {' → '}<span className="text-text-primary font-medium">{impressionsFormed + ownerMemories}</span> knowledge items learned
          </p>
        </div>
      </div>
    </div>
  );
}
