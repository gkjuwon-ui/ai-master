'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts';
import { DollarSign, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface CommunityROIProps {
  totalSpent: number;
  totalEarned: number;
  netROI: number;
  successRate: number;
  knowledgeGained: number;
  impressionsFormed: number;
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-bg-elevated border border-border-primary rounded-lg p-3 shadow-lg">
      <p className="text-xs font-medium text-text-primary mb-1">{d.label}</p>
      <p className="text-xs text-text-secondary">
        {d.value.toLocaleString()} credits
      </p>
    </div>
  );
};

export function CommunityROI({
  totalSpent,
  totalEarned,
  netROI,
  successRate,
  knowledgeGained,
  impressionsFormed,
}: CommunityROIProps) {
  const roiData = [
    { label: 'Spent', value: totalSpent, color: '#ef4444' },
    { label: 'Earned', value: totalEarned, color: '#22c55e' },
  ];

  const roiPercent = totalSpent > 0
    ? Math.round((totalEarned / totalSpent) * 100)
    : 0;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold flex items-center gap-2">
          <DollarSign size={16} className="text-success" />
          Community ROI
        </h3>
        <div className={`flex items-center gap-1 text-xs font-medium ${
          netROI > 0 ? 'text-success' : netROI < 0 ? 'text-error' : 'text-text-tertiary'
        }`}>
          {netROI > 0 ? <TrendingUp size={12} /> : netROI < 0 ? <TrendingDown size={12} /> : <Minus size={12} />}
          {netROI >= 0 ? '+' : ''}{netROI} net
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="p-3 rounded-lg bg-bg-elevated text-center">
          <div className="text-lg font-bold text-error">{totalSpent}</div>
          <div className="text-[10px] text-text-tertiary">Credits Spent</div>
        </div>
        <div className="p-3 rounded-lg bg-bg-elevated text-center">
          <div className="text-lg font-bold text-success">{totalEarned}</div>
          <div className="text-[10px] text-text-tertiary">Credits Earned</div>
        </div>
        <div className="p-3 rounded-lg bg-bg-elevated text-center">
          <div className={`text-lg font-bold ${roiPercent >= 100 ? 'text-success' : 'text-warning'}`}>
            {roiPercent}%
          </div>
          <div className="text-[10px] text-text-tertiary">Return Rate</div>
        </div>
      </div>

      <div className="h-32 mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={roiData} barSize={40}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: '#999' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#666' }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {roiData.map((entry, i) => (
                <Cell key={i} fill={entry.color} fillOpacity={0.8} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-bg-elevated/50">
          <span className="text-xs text-text-secondary">Execution Success Rate</span>
          <span className="text-xs font-semibold text-text-primary">{successRate}%</span>
        </div>
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-bg-elevated/50">
          <span className="text-xs text-text-secondary">Knowledge Items Gained</span>
          <span className="text-xs font-semibold text-text-primary">{knowledgeGained}</span>
        </div>
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-bg-elevated/50">
          <span className="text-xs text-text-secondary">Social Relations Formed</span>
          <span className="text-xs font-semibold text-text-primary">{impressionsFormed}</span>
        </div>
      </div>
    </div>
  );
}
