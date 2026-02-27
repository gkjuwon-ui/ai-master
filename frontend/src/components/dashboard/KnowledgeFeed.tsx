'use client';

import { Brain, BookOpen, Users, MessageCircle } from 'lucide-react';

interface KnowledgeData {
  ownerMemories: number;
  impressionsFormed: number;
  recentImpressions: { targetName: string; sentiment: number; topics: string[] }[];
  recentOwnerMemories: { category: string; content: string; createdAt: string }[];
}

interface KnowledgeFeedProps {
  data: KnowledgeData;
  agentName: string;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  PREFERENCE: <BookOpen size={12} />,
  PERSONALITY: <Users size={12} />,
  HABIT: <Brain size={12} />,
  default: <MessageCircle size={12} />,
};

const CATEGORY_COLORS: Record<string, string> = {
  PREFERENCE: '#3b82f6',
  PERSONALITY: '#a855f7',
  HABIT: '#22c55e',
  OBSERVATION: '#f59e0b',
  default: '#6b7280',
};

function SentimentBadge({ value }: { value: number }) {
  if (value > 0.3) return <span className="text-[10px] px-1.5 py-0.5 rounded bg-success/20 text-success">Positive</span>;
  if (value < -0.3) return <span className="text-[10px] px-1.5 py-0.5 rounded bg-error/20 text-error">Negative</span>;
  return <span className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-tertiary">Neutral</span>;
}

export function KnowledgeFeed({ data, agentName }: KnowledgeFeedProps) {
  const totalKnowledge = data.ownerMemories + data.impressionsFormed;
  const allItems = [
    ...data.recentOwnerMemories.map(m => ({
      type: 'memory' as const,
      category: m.category,
      content: m.content,
      time: m.createdAt,
    })),
    ...data.recentImpressions.map(imp => ({
      type: 'impression' as const,
      category: 'SOCIAL',
      content: `Formed impression of ${imp.targetName}${imp.topics.length > 0 ? ` (${imp.topics.slice(0, 2).join(', ')})` : ''}`,
      time: '',
      sentiment: imp.sentiment,
    })),
  ].slice(0, 6);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold flex items-center gap-2">
          <Brain size={16} className="text-purple-400" />
          Knowledge Feed
        </h3>
        <span className="text-xs text-text-tertiary">
          {totalKnowledge} total items learned
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-bg-elevated">
          <div className="text-lg font-bold">{data.ownerMemories}</div>
          <div className="text-xs text-text-tertiary">Owner Memories</div>
        </div>
        <div className="p-3 rounded-lg bg-bg-elevated">
          <div className="text-lg font-bold">{data.impressionsFormed}</div>
          <div className="text-xs text-text-tertiary">Social Impressions</div>
        </div>
      </div>

      {allItems.length > 0 ? (
        <div className="space-y-2">
          {allItems.map((item, i) => {
            const color = CATEGORY_COLORS[item.category] || CATEGORY_COLORS.default;
            const icon = CATEGORY_ICONS[item.category] || CATEGORY_ICONS.default;
            return (
              <div key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg bg-bg-elevated/50">
                <div
                  className="w-6 h-6 rounded flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ backgroundColor: `${color}20`, color }}
                >
                  {icon}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span
                      className="text-[10px] font-medium px-1.5 py-0.5 rounded"
                      style={{ backgroundColor: `${color}15`, color }}
                    >
                      {item.category}
                    </span>
                    {item.type === 'impression' && 'sentiment' in item && (
                      <SentimentBadge value={(item as any).sentiment} />
                    )}
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed truncate">{item.content}</p>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-6 text-text-tertiary text-xs">
          <Brain size={20} className="mx-auto mb-2 opacity-30" />
          Agent is still learning...
        </div>
      )}
    </div>
  );
}
