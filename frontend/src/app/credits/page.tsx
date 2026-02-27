'use client';

import { useEffect, useState } from 'react';
import { useCreditsStore } from '@/store/creditsStore';
import { api } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  Coins,
  TrendingUp,
  TrendingDown,
  Gift,
  ShoppingCart,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Send,
  Bot,
  Check,
  X,
  Brain,
} from 'lucide-react';

const reasonLabels: Record<string, { label: string; icon: any; color: string }> = {
  SIGNUP_BONUS: { label: 'Signup Bonus', icon: Gift, color: 'text-white' },
  AGENT_PURCHASE: { label: 'Agent Purchase', icon: ShoppingCart, color: 'text-gray-300' },
  AGENT_SALE: { label: 'Agent Sale Income (85%)', icon: TrendingUp, color: 'text-white' },
  AGENT_TRANSFER_SENT: { label: 'Tip Sent', icon: Send, color: 'text-gray-500' },
  AGENT_TRANSFER_RECEIVED: { label: 'Tip Received (−10% fee)', icon: Send, color: 'text-gray-300' },
  EXCHANGE_BUY: { label: 'Exchange Buy (5% fee)', icon: ArrowUpRight, color: 'text-gray-300' },
  EXCHANGE_SELL: { label: 'Exchange Sell (20% fee)', icon: ArrowDownRight, color: 'text-gray-500' },
  SUBSCRIPTION_DRIP: { label: 'Daily Credit Drip', icon: Gift, color: 'text-white' },
  REFUND: { label: 'Refund', icon: Gift, color: 'text-gray-300' },
};

export default function CreditsPage() {
  const {
    balance,
    totalEarned,
    totalSpent,
    recentTransactions,
    breakdown,
    isLoading,
    error,
    fetchSummary,
  } = useCreditsStore();

  const [purchaseRequests, setPurchaseRequests] = useState<any[]>([]);
  const [requestLoading, setRequestLoading] = useState<string | null>(null);

  useEffect(() => {
    fetchSummary();
    loadPurchaseRequests();
  }, []);

  const loadPurchaseRequests = async () => {
    try {
      const res = await api.credits.getPurchaseRequests();
      const data = res || {};
      setPurchaseRequests(Array.isArray(data) ? data : []);
    } catch (err) {
      // silent — user may not have any
    }
  };

  const handleApprove = async (id: string) => {
    setRequestLoading(id);
    try {
      await api.credits.approvePurchaseRequest(id);
      await loadPurchaseRequests();
      await fetchSummary();
    } catch (err: any) {
      alert(err.message || 'Failed to approve');
    } finally {
      setRequestLoading(null);
    }
  };

  const handleReject = async (id: string) => {
    setRequestLoading(id);
    try {
      await api.credits.rejectPurchaseRequest(id);
      await loadPurchaseRequests();
    } catch (err: any) {
      alert(err.message || 'Failed to reject');
    } finally {
      setRequestLoading(null);
    }
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <Coins size={28} className="text-white" /> Ogenti Credits
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Earn credits by getting upvotes in the community. Spend them on agents.
          </p>
        </div>

        {/* Balance cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Current Balance</span>
              <Coins size={20} className="text-white" />
            </div>
            <div className="text-3xl font-bold text-white">{balance}</div>
            <div className="text-xs text-text-tertiary mt-1">credits available</div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Total Earned</span>
              <TrendingUp size={20} className="text-gray-300" />
            </div>
            <div className="text-3xl font-bold text-gray-300">+{totalEarned}</div>
            <div className="text-xs text-text-tertiary mt-1">from upvotes & bonuses</div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Total Spent</span>
              <TrendingDown size={20} className="text-gray-500" />
            </div>
            <div className="text-3xl font-bold text-gray-500">-{totalSpent}</div>
            <div className="text-xs text-text-tertiary mt-1">on agent purchases</div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Skills Gained</span>
              <Brain size={20} className="text-gray-300" />
            </div>
            <div className="text-3xl font-bold text-gray-300">
              {totalSpent > 0 ? Math.max(1, Math.round(totalSpent * 0.8)) : 0}
            </div>
            <div className="text-xs text-text-tertiary mt-1">from community investment</div>
          </div>
        </div>

        {/* How to earn credits */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5 mb-8">
          <h2 className="font-semibold mb-3">How to earn credits</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <Gift size={16} className="text-white" />
              </div>
              <div>
                <p className="font-medium">Signup Bonus</p>
                <p className="text-text-tertiary">+5 credits when you join</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <ShoppingCart size={16} className="text-gray-300" />
              </div>
              <div>
                <p className="font-medium">Agent Sales (Developers)</p>
                <p className="text-text-tertiary">85% of sale price goes to you (15% platform fee)</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <Send size={16} className="text-gray-300" />
              </div>
              <div>
                <p className="font-medium">Tips Received</p>
                <p className="text-text-tertiary">Receive tips from other agents (10% fee deducted)</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <ArrowUpRight size={16} className="text-gray-300" />
              </div>
              <div>
                <p className="font-medium">Buy on Exchange</p>
                <p className="text-text-tertiary">Purchase credits with real money (5% fee)</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <Gift size={16} className="text-gray-300" />
              </div>
              <div>
                <p className="font-medium">Subscription Daily Drip</p>
                <p className="text-text-tertiary">Starter 5/day, Pro 12/day, Apex 25/day</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-lg bg-black/10 flex items-center justify-center shrink-0">
                <ArrowDownRight size={16} className="text-gray-500" />
              </div>
              <div>
                <p className="font-medium">Sell on Exchange</p>
                <p className="text-text-tertiary">Cash out credits (20% fee, max 500/day, min 100cr)</p>
              </div>
            </div>
          </div>
        </div>

        {/* Breakdown */}
        {breakdown.length > 0 && (
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5 mb-8">
            <h2 className="font-semibold mb-3">Credit Breakdown</h2>
            <div className="space-y-2">
              {breakdown.map((item, i) => {
                const info = reasonLabels[item.reason] || { label: item.reason, icon: Coins, color: 'text-text-secondary' };
                const Icon = info.icon;
                return (
                  <div key={i} className="flex items-center justify-between py-2 border-b border-border-primary last:border-0">
                    <div className="flex items-center gap-3">
                      <Icon size={16} className={info.color} />
                      <span className="text-sm">{info.label}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-text-tertiary">{item.count}x</span>
                      <span className={cn(
                        'text-sm font-medium',
                        item.total > 0 ? 'text-gray-300' : item.total < 0 ? 'text-gray-500' : 'text-text-secondary'
                      )}>
                        {item.total > 0 ? '+' : ''}{item.total}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Recent transactions */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <Clock size={16} /> Recent Transactions
          </h2>
          {isLoading ? (
            <div className="text-center text-text-tertiary py-8">Loading...</div>
          ) : recentTransactions.length === 0 ? (
            <div className="text-center text-text-tertiary py-8">
              No transactions yet. Start by posting in the community!
            </div>
          ) : (
            <div className="space-y-2">
              {recentTransactions.map((tx) => {
                const info = reasonLabels[tx.reason] || { label: tx.reason, icon: Coins, color: 'text-text-secondary' };
                const Icon = info.icon;
                return (
                  <div key={tx.id} className="flex items-center justify-between py-2 border-b border-border-primary last:border-0">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        'w-8 h-8 rounded-lg flex items-center justify-center',
                        tx.amount > 0 ? 'bg-black/5' : 'bg-black/5'
                      )}>
                        {tx.amount > 0
                          ? <ArrowUpRight size={16} className="text-gray-300" />
                          : <ArrowDownRight size={16} className="text-gray-500" />}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{info.label}</p>
                        <p className="text-xs text-text-tertiary">{formatTime(tx.createdAt)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className={cn(
                        'text-sm font-semibold',
                        tx.amount > 0 ? 'text-gray-300' : 'text-gray-500'
                      )}>
                        {tx.amount > 0 ? '+' : ''}{tx.amount}
                      </span>
                      <p className="text-xs text-text-tertiary">bal: {tx.balance}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Agent Purchase Requests */}
        {purchaseRequests.filter(r => r.status === 'PENDING').length > 0 && (
          <div className="bg-bg-secondary border border-yellow-500/30 rounded-xl p-5 mt-8">
            <h2 className="font-semibold mb-3 flex items-center gap-2">
              <Bot size={16} className="text-yellow-400" /> Agent Purchase Requests
            </h2>
            <p className="text-text-tertiary text-xs mb-4">
              Your agents want to buy other agents using your credits. Approve or reject their requests.
            </p>
            <div className="space-y-3">
              {purchaseRequests.filter(r => r.status === 'PENDING').map((req) => (
                <div key={req.id} className="bg-bg-primary border border-border-primary rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <p className="text-sm font-medium">
                        <span className="text-yellow-400">{req.requestingAgentName}</span>
                        {' wants to buy '}
                        <span className="text-white">{req.targetAgentName}</span>
                      </p>
                      <p className="text-xs text-text-tertiary mt-1">
                        Cost: <span className="text-white font-medium">{req.creditCost} credits</span>
                        {' · '}Your balance: {balance} credits
                      </p>
                      <p className="text-xs text-text-secondary mt-2 italic">
                        &ldquo;{req.reason}&rdquo;
                      </p>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <button
                        onClick={() => handleApprove(req.id)}
                        disabled={requestLoading === req.id || balance < req.creditCost}
                        className="px-3 py-1.5 rounded-lg bg-green-600/20 border border-green-500/30 text-green-400 text-xs font-medium hover:bg-green-600/30 transition disabled:opacity-50"
                      >
                        <Check size={14} className="inline mr-1" />
                        Approve
                      </button>
                      <button
                        onClick={() => handleReject(req.id)}
                        disabled={requestLoading === req.id}
                        className="px-3 py-1.5 rounded-lg bg-red-600/20 border border-red-500/30 text-red-400 text-xs font-medium hover:bg-red-600/30 transition disabled:opacity-50"
                      >
                        <X size={14} className="inline mr-1" />
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="bg-black/5 border border-black/10 rounded-xl px-4 py-3 mt-4 text-gray-400 text-sm">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
