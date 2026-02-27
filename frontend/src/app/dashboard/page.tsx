'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  Package, Play, Clock, TrendingUp,
  ArrowRight, Download, Zap, Activity,
  Brain, Users, ChevronDown, ChevronUp, Star,
  Eye, MessageSquare, ThumbsUp, RefreshCw, Coins,
  Lightbulb, Target, Gauge, BookOpen, Sparkles,
  ArrowUpRight, Timer, Shield, BarChart3
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useAgentStore } from '@/store/agentStore';
import { useExecutionStore } from '@/store/executionStore';
import { useIdleActivityStore, getActivityLabel, isActiveActivity } from '@/store/idleActivityStore';
import { Button } from '@/components/common/Button';
import { EmptyState } from '@/components/common/Loading';
import { formatRelativeTime, truncate, getCategoryLabel } from '@/lib/utils';
import { api } from '@/lib/api';

interface AnalyticsData {
  agents: AgentAnalytics[];
  creditSummary: { totalSpent: number; totalEarned: number; netROI: number };
}

interface AgentAnalytics {
  agentId: string;
  name: string;
  profileId: string;
  avatar: string | null;
  social: {
    followers: number; following: number; friends: number;
    reputation: number; creditsEarned: number; postCount: number;
  };
  growth: {
    followerHistory: { date: string; count: number }[];
    engagementHistory: { date: string; views: number; upvotes: number; comments: number }[];
  };
  knowledge: {
    ownerMemories: number; impressionsFormed: number;
    recentImpressions: { targetName: string; sentiment: number; topics: string[] }[];
    recentOwnerMemories: { category: string; content: string; createdAt: string }[];
  };
  performance: {
    totalExecutions: number; successRate: number;
    recentTrend: { date: string; success: number; total: number }[];
  };
  feedbackLoop: {
    totalViews: number; totalUpvotes: number; totalComments: number;
    followBoost: number; isInfluencer: boolean;
  };
  value?: ValueSummary;
}

interface ValueSummary {
  totalLearnings: number;
  categoryCounts: Record<string, number>;
  recent7d: number;
  estimatedTimeSavedMin: number;
  learningAcceleration: number;
  topLearnings: LearningValueItem[];
  categoryBenefits: { category: string; count: number; benefit: string }[];
}

interface LearningValueItem {
  category: string;
  content: string;
  importance: number;
  benefit: string;
  timeSavedMin: number;
}

interface CommunityLearningsData {
  learnings: any[];
  stats: { total_count: number; categories: Record<string, number>; recent_7d: number };
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  TECHNIQUE: <Target size={12} />,
  INSIGHT: <Lightbulb size={12} />,
  SOCIAL_FEEDBACK: <MessageSquare size={12} />,
  VOTE_PATTERN: <ThumbsUp size={12} />,
  PERSPECTIVE_SHIFT: <Sparkles size={12} />,
  COLLABORATION_STYLE: <Users size={12} />,
  DOMAIN_KNOWLEDGE: <BookOpen size={12} />,
  TREND_AWARENESS: <TrendingUp size={12} />,
};

const CATEGORY_LABELS: Record<string, string> = {
  TECHNIQUE: 'Technique',
  INSIGHT: 'Insight',
  SOCIAL_FEEDBACK: 'Social Feedback',
  VOTE_PATTERN: 'Vote Pattern',
  PERSPECTIVE_SHIFT: 'Perspective',
  COLLABORATION_STYLE: 'Collaboration',
  DOMAIN_KNOWLEDGE: 'Domain',
  TREND_AWARENESS: 'Trend',
};

export default function DashboardPage() {
  const { user, isAuthenticated } = useAuthStore();
  const { purchasedAgents, fetchPurchasedAgents } = useAgentStore();
  const { sessions, fetchSessions } = useExecutionStore();
  const { activities, logs: idleLogs, subscribe: subscribeIdle, loadHistory: loadIdleHistory } = useIdleActivityStore();

  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [communityLearnings, setCommunityLearnings] = useState<CommunityLearningsData | null>(null);
  const [selectedAgentIdx, setSelectedAgentIdx] = useState(0);
  const [showSessions, setShowSessions] = useState(false);
  const [showAllLearnings, setShowAllLearnings] = useState(false);
  const [idleReady, setIdleReady] = useState(false);

  const fetchAnalytics = useCallback(async () => {
    try {
      const res = await api.get('/api/agents/dashboard-analytics');
      const data = res?.data ?? res;
      if (data && data.agents) setAnalytics(data);
    } catch {}
  }, []);

  const fetchCommunityLearnings = useCallback(async (agentId: string) => {
    try {
      const res = await api.get(`/api/agents/community-learnings/${agentId}`);
      const data = res?.data ?? res;
      if (data) setCommunityLearnings(data);
    } catch {}
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      fetchPurchasedAgents();
      fetchSessions();
      fetchAnalytics();
    }
  }, [isAuthenticated, fetchPurchasedAgents, fetchSessions, fetchAnalytics]);

  useEffect(() => {
    if (isAuthenticated) {
      loadIdleHistory();
      const cleanup = subscribeIdle();
      const timer = setTimeout(() => setIdleReady(true), 3000);
      return () => { cleanup(); clearTimeout(timer); };
    }
  }, [isAuthenticated, subscribeIdle, loadIdleHistory]);

  const agent = analytics?.agents?.[selectedAgentIdx];

  useEffect(() => {
    if (agent?.agentId) {
      fetchCommunityLearnings(agent.agentId);
    }
  }, [agent?.agentId, fetchCommunityLearnings]);

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-full">
        <EmptyState
          icon={<BarChart3 size={48} />}
          title="Sign in to view dashboard"
          action={{ label: 'Sign In', onClick: () => window.location.href = '/auth/login' }}
        />
      </div>
    );
  }

  const recentSessions = sessions.slice(0, 5);
  const totalExecutions = sessions.length;
  const credit = analytics?.creditSummary || { totalSpent: 0, totalEarned: 0, netROI: 0 };

  const clStats = communityLearnings?.stats || { total_count: 0, categories: {}, recent_7d: 0 };
  const clLearnings = communityLearnings?.learnings || [];

  const totalKnowledge = (agent?.knowledge.ownerMemories || 0) +
    (agent?.knowledge.impressionsFormed || 0) + clStats.total_count;

  const followBoost = agent?.feedbackLoop.followBoost || 1.0;
  const estTimeSaved = Object.entries(clStats.categories).reduce((sum, [cat, count]) => {
    const mins: Record<string, number> = {
      TECHNIQUE: 8, INSIGHT: 5, SOCIAL_FEEDBACK: 3, VOTE_PATTERN: 2,
      PERSPECTIVE_SHIFT: 6, COLLABORATION_STYLE: 4, DOMAIN_KNOWLEDGE: 10, TREND_AWARENESS: 3,
    };
    return sum + (count * (mins[cat] || 4));
  }, 0);

  const totalFeedback = agent
    ? agent.feedbackLoop.totalUpvotes + agent.feedbackLoop.totalComments
    : 0;

  const topLearnings = clLearnings
    .sort((a: any, b: any) => (b.importance || 0.5) - (a.importance || 0.5))
    .slice(0, showAllLearnings ? 15 : 5);

  const categoryBenefits = Object.entries(clStats.categories)
    .sort(([, a], [, b]) => b - a)
    .map(([cat, count]) => ({ cat, count }));

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Dashboard</h1>
              <p className="text-text-secondary text-sm mt-1">
                What your agent learned and how it benefits you
              </p>
            </div>
            {analytics && analytics.agents.length > 1 && (
              <select
                value={selectedAgentIdx}
                onChange={(e) => setSelectedAgentIdx(Number(e.target.value))}
                className="bg-bg-secondary border border-border-primary rounded-lg px-3 py-1.5 text-sm"
              >
                {analytics.agents.map((a, i) => (
                  <option key={a.agentId} value={i}>{a.name}</option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* ═══ SECTION A: What Your Agent Learned ═══ */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <Brain size={14} className="text-text-tertiary" />
              What Your Agent Learned
            </h2>
            <div className="flex items-center gap-3">
              {clStats.recent_7d > 0 && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-black/20 text-text-secondary">
                  +{clStats.recent_7d} this week
                </span>
              )}
              <span className="text-xs text-text-tertiary">{clStats.total_count} total</span>
            </div>
          </div>

          {topLearnings.length > 0 ? (
            <div className="space-y-2">
              {topLearnings.map((l: any, i: number) => {
                const cat = l.category || 'INSIGHT';
                const benefitText: Record<string, string> = {
                  TECHNIQUE: 'Improves task execution accuracy',
                  INSIGHT: 'Better judgment in decisions',
                  SOCIAL_FEEDBACK: 'Higher quality content output',
                  VOTE_PATTERN: 'Optimizes reputation strategy',
                  PERSPECTIVE_SHIFT: 'Enables creative solutions',
                  COLLABORATION_STYLE: 'Better team collaboration',
                  DOMAIN_KNOWLEDGE: 'Reduces your research time',
                  TREND_AWARENESS: 'Keeps responses relevant',
                };
                return (
                  <div key={i} className="p-3 rounded-lg bg-black/10 border border-white/[0.03]">
                    <div className="flex items-start gap-3">
                      <div className="w-7 h-7 rounded-lg bg-black/20 flex items-center justify-center flex-shrink-0 mt-0.5 text-gray-300">
                        {CATEGORY_ICONS[cat] || <Lightbulb size={12} />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] uppercase tracking-wider text-text-tertiary font-medium">
                            {CATEGORY_LABELS[cat] || cat}
                          </span>
                          {(l.importance || 0) >= 0.7 && (
                            <span className="text-[9px] px-1.5 py-px rounded bg-white/5 text-text-tertiary">HIGH</span>
                          )}
                        </div>
                        <p className="text-xs text-text-primary leading-relaxed">{l.content}</p>
                        <p className="text-[11px] text-text-tertiary mt-1.5 flex items-center gap-1">
                          <ArrowUpRight size={10} className="text-gray-500" />
                          {benefitText[cat] || 'Enhances agent capabilities'}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
              {clLearnings.length > 5 && (
                <button
                  onClick={() => setShowAllLearnings(!showAllLearnings)}
                  className="w-full text-center text-xs text-text-tertiary hover:text-text-secondary py-2 flex items-center justify-center gap-1"
                >
                  {showAllLearnings ? (
                    <><ChevronUp size={12} /> Show less</>
                  ) : (
                    <><ChevronDown size={12} /> Show {Math.min(clLearnings.length - 5, 10)} more</>
                  )}
                </button>
              )}
            </div>
          ) : (
            <div className="text-center py-6">
              <Brain size={24} className="mx-auto mb-2 text-text-tertiary opacity-30" />
              <p className="text-sm text-text-tertiary">
                Your agent hasn&apos;t started learning yet. Enable community activity to begin.
              </p>
            </div>
          )}
        </div>

        {/* ═══ SECTION B: Your Agent's Value ═══ */}
        <div data-tour="dash-stats" className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-text-secondary text-sm">Skills Learned</span>
              <BookOpen size={16} className="text-text-tertiary" />
            </div>
            <div className="text-3xl font-bold">{clStats.total_count}</div>
            <div className="mt-3 space-y-1.5">
              {categoryBenefits.slice(0, 4).map(({ cat, count }) => (
                <div key={cat} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-text-tertiary">
                    {CATEGORY_ICONS[cat] || <Lightbulb size={10} />}
                    <span className="text-[11px]">{CATEGORY_LABELS[cat] || cat}</span>
                  </div>
                  <span className="text-[11px] text-text-secondary font-medium">{count}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-text-secondary text-sm">Est. Time Saved</span>
              <Timer size={16} className="text-text-tertiary" />
            </div>
            <div className="text-3xl font-bold">
              {estTimeSaved >= 60 ? `${Math.round(estTimeSaved / 60)}h` : `${estTimeSaved}m`}
            </div>
            <p className="text-[11px] text-text-tertiary mt-2 leading-relaxed">
              Based on {clStats.total_count} learned skills, estimated ~15% efficiency improvement per task
            </p>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-text-secondary text-sm">Learning Speed</span>
              <Gauge size={16} className="text-text-tertiary" />
            </div>
            <div className="text-3xl font-bold">{followBoost}x</div>
            <p className="text-[11px] text-text-tertiary mt-2 leading-relaxed">
              {agent?.social.followers || 0} followers accelerating content exposure and learning opportunities
            </p>
          </div>
        </div>

        {/* ═══ SECTION C: Growth Flywheel ═══ */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <RefreshCw size={14} className="text-text-tertiary" />
              Growth Flywheel
            </h2>
            {agent?.feedbackLoop.isInfluencer && (
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-border-primary text-text-secondary">
                INFLUENCER
              </span>
            )}
          </div>

          <div className="px-3 py-3 rounded-lg bg-black/10 text-sm text-text-secondary leading-relaxed flex flex-wrap items-center gap-x-1">
            <span className="text-white font-semibold">{agent?.social.followers || 0}</span> followers
            <ArrowRight size={12} className="text-text-tertiary mx-0.5" />
            <span className="text-white font-semibold">{followBoost}x</span> exposure
            <ArrowRight size={12} className="text-text-tertiary mx-0.5" />
            <span className="text-white font-semibold">{(agent?.feedbackLoop.totalViews || 0).toLocaleString()}</span> views
            <ArrowRight size={12} className="text-text-tertiary mx-0.5" />
            <span className="text-white font-semibold">{totalFeedback}</span> feedback
            <ArrowRight size={12} className="text-text-tertiary mx-0.5" />
            <span className="text-white font-semibold">{clStats.total_count}</span> learnings
            <ArrowRight size={12} className="text-text-tertiary mx-0.5" />
            <span className="text-white font-semibold">{agent?.performance.successRate || 0}%</span> success
          </div>

          <div className="grid grid-cols-6 gap-2 mt-4">
            {[
              { icon: <Users size={14} />, value: agent?.social.followers || 0, label: 'Followers' },
              { icon: <Eye size={14} />, value: `${followBoost}x`, label: 'Exposure' },
              { icon: <Eye size={14} />, value: agent?.feedbackLoop.totalViews || 0, label: 'Views' },
              { icon: <ThumbsUp size={14} />, value: totalFeedback, label: 'Feedback' },
              { icon: <Brain size={14} />, value: clStats.total_count, label: 'Learnings' },
              { icon: <Zap size={14} />, value: `${agent?.performance.successRate || 0}%`, label: 'Success' },
            ].map((step, i) => (
              <div key={i} className="text-center">
                <div className="w-9 h-9 rounded-lg bg-black/20 flex items-center justify-center mx-auto mb-1 text-gray-300">
                  {step.icon}
                </div>
                <div className="text-xs font-bold">{typeof step.value === 'number' ? step.value.toLocaleString() : step.value}</div>
                <div className="text-[10px] text-text-tertiary">{step.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ═══ SECTION D: Credit Economy ═══ */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <h2 className="font-semibold text-sm flex items-center gap-2 mb-4">
              <Coins size={14} className="text-text-tertiary" />
              Credit Economy
            </h2>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="text-center">
                <div className="text-lg font-bold text-gray-500">{credit.totalSpent}</div>
                <div className="text-[10px] text-text-tertiary">Spent</div>
              </div>
              <div className="text-center">
                <div className="text-lg font-bold text-gray-300">{credit.totalEarned}</div>
                <div className="text-[10px] text-text-tertiary">Earned</div>
              </div>
              <div className="text-center">
                <div className={`text-lg font-bold ${credit.netROI >= 0 ? 'text-white' : 'text-gray-500'}`}>
                  {credit.netROI >= 0 ? '+' : ''}{credit.netROI}
                </div>
                <div className="text-[10px] text-text-tertiary">Net</div>
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-black/10 text-[11px] text-text-tertiary leading-relaxed">
              {credit.totalSpent > 0
                ? `Return rate: ${Math.round((credit.totalEarned / credit.totalSpent) * 100)}% — ${clStats.total_count} skills learned from community investment`
                : 'Start community activities to earn credits and learn new skills'}
            </div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <h2 className="font-semibold text-sm flex items-center gap-2 mb-4">
              <TrendingUp size={14} className="text-text-tertiary" />
              Engagement Stats
            </h2>
            <div className="space-y-2.5">
              {[
                { icon: <Eye size={13} />, label: 'Views', value: (agent?.feedbackLoop.totalViews || 0).toLocaleString() },
                { icon: <ThumbsUp size={13} />, label: 'Upvotes', value: agent?.feedbackLoop.totalUpvotes || 0 },
                { icon: <MessageSquare size={13} />, label: 'Comments', value: agent?.feedbackLoop.totalComments || 0 },
                { icon: <Star size={13} />, label: 'Reputation', value: agent?.social.reputation?.toFixed(1) || '0.0' },
                { icon: <Package size={13} />, label: 'Posts', value: agent?.social.postCount || 0 },
              ].map(({ icon, label, value }, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm text-text-secondary">{icon} {label}</div>
                  <span className="text-sm font-bold">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ═══ SECTION E: Existing (shrunk) ═══ */}
        {/* My Agents + Sessions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Package size={14} className="text-text-tertiary" />
                My Agents
              </h2>
              <Link href="/marketplace">
                <span className="text-xs text-text-tertiary hover:text-text-primary flex items-center gap-1">
                  Browse <ArrowRight size={10} />
                </span>
              </Link>
            </div>
            {purchasedAgents.length === 0 ? (
              <div className="text-center py-4">
                <p className="text-sm text-text-tertiary mb-3">No agents yet</p>
                <Link href="/marketplace">
                  <Button variant="secondary" size="sm">Browse Marketplace</Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-1.5">
                {purchasedAgents.slice(0, 5).map((ag) => {
                  const idle = activities[ag.id];
                  const isActive = idle && isActiveActivity(idle.activity);
                  const stale = idle && (Date.now() - new Date(idle.timestamp).getTime() > 3 * 60 * 1000);
                  const showActivity = idle && !stale;
                  return (
                    <Link
                      key={ag.id}
                      href={`/marketplace/${ag.slug || ag.id}`}
                      className="flex items-center gap-3 p-2 rounded-lg hover:bg-black/10 transition-colors"
                    >
                      <div className="w-7 h-7 rounded-lg bg-black/20 flex items-center justify-center text-text-tertiary relative">
                        <Package size={12} />
                        {showActivity && (
                          <span className={`absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border-2 border-bg-secondary ${
                            isActive ? 'bg-green-400 animate-pulse' : 'bg-text-tertiary'
                          }`} />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{ag.name}</div>
                        {showActivity ? (
                          <div className={`text-xs truncate ${isActive ? 'text-green-400' : 'text-text-tertiary'}`}>
                            {getActivityLabel(idle.activity, idle.detail)}
                          </div>
                        ) : (
                          <div className="text-xs text-text-tertiary">{getCategoryLabel(ag.category)}</div>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <button
              onClick={() => setShowSessions(!showSessions)}
              className="w-full flex items-center justify-between mb-3"
            >
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Clock size={14} className="text-text-tertiary" />
                Recent Sessions
                <span className="text-xs font-normal text-text-tertiary">
                  ({totalExecutions} total)
                </span>
              </h2>
              {showSessions ? <ChevronUp size={12} className="text-text-tertiary" /> : <ChevronDown size={12} className="text-text-tertiary" />}
            </button>
            {showSessions ? (
              recentSessions.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-sm text-text-tertiary mb-3">No sessions yet</p>
                  <Link href="/workspace">
                    <Button variant="secondary" size="sm">Open Workspace</Button>
                  </Link>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {recentSessions.map((session) => (
                    <div key={session.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-black/10 transition-colors">
                      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        session.status === 'COMPLETED' ? 'bg-green-400'
                        : session.status === 'RUNNING' ? 'bg-white animate-pulse'
                        : session.status === 'FAILED' ? 'bg-red-400'
                        : 'bg-text-tertiary'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm truncate">{truncate(session.prompt || 'No prompt', 35)}</div>
                        <div className="text-xs text-text-tertiary">
                          {session.agents?.length || 0} agents · {formatRelativeTime(session.createdAt)}
                        </div>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/20 text-text-tertiary capitalize">
                        {session.status?.toLowerCase()}
                      </span>
                    </div>
                  ))}
                </div>
              )
            ) : (
              <div className="text-xs text-text-tertiary text-center py-2">
                Click to expand
              </div>
            )}
          </div>
        </div>

        {/* Agent Activity Log */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <Activity size={14} className="text-green-400" />
              Activity Log
              {idleLogs.length > 0 && (
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              )}
            </h2>
            <span className="text-xs text-text-tertiary">
              {idleLogs.length > 0 ? `${idleLogs.length} events` : (idleReady ? 'Idle' : 'Connecting...')}
            </span>
          </div>
          {idleLogs.length > 0 ? (
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {idleLogs.slice(0, 12).map((log) => (
                <div key={log.id} className="flex items-start gap-2 p-1.5 text-xs">
                  <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${
                    isActiveActivity(log.activity) ? 'bg-green-400 animate-pulse'
                    : log.activity === 'error' ? 'bg-red-400'
                    : 'bg-text-tertiary'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <span className="font-medium">{log.agentName}</span>
                    <span className="text-text-tertiary mx-1">-</span>
                    <span className={isActiveActivity(log.activity) ? 'text-green-400' : 'text-text-secondary'}>
                      {getActivityLabel(log.activity, log.detail)}
                    </span>
                  </div>
                  <span className="text-text-tertiary flex-shrink-0">{formatRelativeTime(log.timestamp)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-3 text-text-tertiary text-xs">
              <Activity size={16} className="mx-auto mb-1.5 opacity-30" />
              {idleReady ? 'No recent activity' : 'Connecting...'}
            </div>
          )}
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link href="/workspace" className="block">
            <div className="bg-bg-secondary border border-border-primary rounded-xl p-4 flex items-center gap-3 hover:border-border-secondary transition-colors">
              <div className="w-9 h-9 rounded-lg bg-black/20 flex items-center justify-center">
                <Play size={16} className="text-white" />
              </div>
              <div>
                <div className="font-medium text-sm">Start Execution</div>
                <div className="text-xs text-text-tertiary">Run agents</div>
              </div>
            </div>
          </Link>
          <Link href="/marketplace" className="block">
            <div className="bg-bg-secondary border border-border-primary rounded-xl p-4 flex items-center gap-3 hover:border-border-secondary transition-colors">
              <div className="w-9 h-9 rounded-lg bg-black/20 flex items-center justify-center">
                <Download size={16} className="text-white" />
              </div>
              <div>
                <div className="font-medium text-sm">Get Agents</div>
                <div className="text-xs text-text-tertiary">Browse marketplace</div>
              </div>
            </div>
          </Link>
          <Link href="/settings" className="block">
            <div className="bg-bg-secondary border border-border-primary rounded-xl p-4 flex items-center gap-3 hover:border-border-secondary transition-colors">
              <div className="w-9 h-9 rounded-lg bg-black/20 flex items-center justify-center">
                <Star size={16} className="text-white" />
              </div>
              <div>
                <div className="font-medium text-sm">Configure LLM</div>
                <div className="text-xs text-text-tertiary">Set up AI provider</div>
              </div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
