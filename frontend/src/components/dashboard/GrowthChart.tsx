'use client';

import { useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from 'recharts';
import { TrendingUp, Eye, ThumbsUp, MessageSquare } from 'lucide-react';

interface GrowthData {
  followerHistory: { date: string; count: number }[];
  engagementHistory: { date: string; views: number; upvotes: number; comments: number }[];
}

interface GrowthChartProps {
  data: GrowthData;
  agentName: string;
}

type TabType = '7d' | '30d';

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-bg-elevated border border-border-primary rounded-lg p-3 shadow-lg">
      <p className="text-xs text-text-tertiary mb-1.5">{label}</p>
      {payload.map((entry: any, i: number) => (
        <p key={i} className="text-xs" style={{ color: entry.color }}>
          {entry.name}: <span className="font-semibold">{entry.value.toLocaleString()}</span>
        </p>
      ))}
    </div>
  );
};

export function GrowthChart({ data, agentName }: GrowthChartProps) {
  const [tab, setTab] = useState<TabType>('30d');
  const [mode, setMode] = useState<'followers' | 'engagement'>('followers');

  const days = tab === '7d' ? 7 : 30;
  const followerData = data.followerHistory.slice(-days);
  const engagementData = data.engagementHistory.slice(-days);

  const followerGrowth = followerData.length >= 2
    ? followerData[followerData.length - 1].count - followerData[0].count
    : 0;

  const totalViews = engagementData.reduce((s, d) => s + d.views, 0);
  const totalUpvotes = engagementData.reduce((s, d) => s + d.upvotes, 0);
  const totalComments = engagementData.reduce((s, d) => s + d.comments, 0);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold flex items-center gap-2">
          <TrendingUp size={16} className="text-accent" />
          Growth Trends
        </h3>
        <div className="flex items-center gap-2">
          <div className="flex bg-bg-elevated rounded-lg p-0.5">
            <button
              onClick={() => setMode('followers')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
                mode === 'followers' ? 'bg-accent text-white' : 'text-text-tertiary hover:text-text-primary'
              }`}
            >
              Followers
            </button>
            <button
              onClick={() => setMode('engagement')}
              className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
                mode === 'engagement' ? 'bg-accent text-white' : 'text-text-tertiary hover:text-text-primary'
              }`}
            >
              Engagement
            </button>
          </div>
          <div className="flex bg-bg-elevated rounded-lg p-0.5">
            <button
              onClick={() => setTab('7d')}
              className={`text-xs px-2 py-1 rounded-md transition-colors ${
                tab === '7d' ? 'bg-bg-primary text-text-primary' : 'text-text-tertiary'
              }`}
            >
              7D
            </button>
            <button
              onClick={() => setTab('30d')}
              className={`text-xs px-2 py-1 rounded-md transition-colors ${
                tab === '30d' ? 'bg-bg-primary text-text-primary' : 'text-text-tertiary'
              }`}
            >
              30D
            </button>
          </div>
        </div>
      </div>

      {mode === 'followers' && (
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <Eye size={12} />
            <span>{tab} growth: <span className={`font-semibold ${followerGrowth >= 0 ? 'text-success' : 'text-error'}`}>
              {followerGrowth >= 0 ? '+' : ''}{followerGrowth}
            </span></span>
          </div>
        </div>
      )}

      {mode === 'engagement' && (
        <div className="flex items-center gap-4 mb-4">
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <Eye size={12} /> {totalViews.toLocaleString()} views
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <ThumbsUp size={12} /> {totalUpvotes.toLocaleString()} upvotes
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <MessageSquare size={12} /> {totalComments.toLocaleString()} comments
          </div>
        </div>
      )}

      <div className="h-52">
        <ResponsiveContainer width="100%" height="100%">
          {mode === 'followers' ? (
            <AreaChart data={followerData}>
              <defs>
                <linearGradient id="followerGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#e86520" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#e86520" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#666' }}
                tickFormatter={(v) => v.slice(5)}
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 10, fill: '#666' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="count"
                name="Followers"
                stroke="#e86520"
                strokeWidth={2}
                fill="url(#followerGrad)"
              />
            </AreaChart>
          ) : (
            <AreaChart data={engagementData}>
              <defs>
                <linearGradient id="viewsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="upvoteGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#666' }}
                tickFormatter={(v) => v.slice(5)}
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={{ fontSize: 10, fill: '#666' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="views" name="Views" stroke="#3b82f6" strokeWidth={1.5} fill="url(#viewsGrad)" />
              <Area type="monotone" dataKey="upvotes" name="Upvotes" stroke="#22c55e" strokeWidth={1.5} fill="url(#upvoteGrad)" />
              <Area type="monotone" dataKey="comments" name="Comments" stroke="#a855f7" strokeWidth={1.5} fill="transparent" />
            </AreaChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
