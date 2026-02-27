'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useCreditsStore } from '@/store/creditsStore';
import { cn } from '@/lib/utils';
import { CreditPaymentModal } from '@/components/common/CreditPaymentModal';
import {
  ArrowRightLeft,
  DollarSign,
  Coins,
  TrendingUp,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Info,
  Loader2,
  CreditCard,
} from 'lucide-react';

interface ExchangeRateData {
  rate: number;
  creditPrice: number;
  buyFeeRate: number;
  sellFeeRate: number;
  buyExample: { credits: number; cost: number; fee: number; total: number };
  sellExample: { credits: number; payout: number; fee: number; net: number };
  dailySellLimit: number;
  minBalanceAfterSell: number;
}

interface ExchangeRecord {
  id: string;
  type: 'BUY' | 'SELL';
  creditAmount: number;
  moneyAmount: number;
  exchangeRate: number;
  fee: number;
  netMoney: number;
  status: string;
  createdAt: string;
}

export default function ExchangePage() {
  const { balance, fetchBalance } = useCreditsStore();
  const [rateData, setRateData] = useState<ExchangeRateData | null>(null);
  const [history, setHistory] = useState<ExchangeRecord[]>([]);
  const [activeTab, setActiveTab] = useState<'buy' | 'sell'>('buy');
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [rateLoading, setRateLoading] = useState(true);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [stripeEnabled, setStripeEnabled] = useState(false);
  const [stripeLoading, setStripeLoading] = useState(false);
  const [bankAccount, setBankAccount] = useState('');
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [paymentCreditAmount, setPaymentCreditAmount] = useState(0);

  useEffect(() => {
    fetchBalance();
    loadRate();
    loadHistory();
    checkStripe();
  }, []);

  const checkStripe = async () => {
    try {
      const res = await api.stripe.getStatus();
      const data = res || {};
      setStripeEnabled(data.enabled === true);
    } catch { /* silent */ }
  };

  const loadRate = async () => {
    try {
      setRateLoading(true);
      const res = await api.exchange.getRate();
      setRateData(res || {});
    } catch (err: any) {
      setError(err.message);
    } finally {
      setRateLoading(false);
    }
  };

  const loadHistory = async () => {
    try {
      const res = await api.exchange.getHistory();
      const data = res || {};
      setHistory(data.exchanges || []);
    } catch (err: any) {
      // silent
    }
  };

  const handleExchange = async () => {
    const creditAmount = parseInt(amount);
    if (!creditAmount || creditAmount <= 0) {
      setError('Enter a valid credit amount');
      return;
    }

    if (activeTab === 'sell' && !bankAccount.trim()) {
      setError('Enter a bank account for payout');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let res;
      if (activeTab === 'buy') {
        res = await api.exchange.buy(creditAmount);
      } else {
        res = await api.exchange.sell(creditAmount);
      }
      const data = res || {};
      setResult(data);
      setAmount('');
      await fetchBalance();
      await loadRate();
      await loadHistory();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleStripeCheckout = async () => {
    const creditAmount = parseInt(amount);
    if (!creditAmount || creditAmount < 5) {
      setError('Minimum 5 credits required');
      return;
    }
    setPaymentCreditAmount(creditAmount);
    setShowPaymentModal(true);
  };

  const handlePaymentSuccess = async () => {
    setShowPaymentModal(false);
    setPaymentCreditAmount(0);
    setAmount('');
    setResult({ type: 'BUY', creditAmount: paymentCreditAmount, status: 'COMPLETED' });
    await fetchBalance();
    await loadRate();
    await loadHistory();
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const previewAmount = parseInt(amount) || 0;
  const buyPreview = rateData && previewAmount > 0 && activeTab === 'buy'
    ? {
        baseCost: previewAmount / rateData.rate,
        fee: (previewAmount / rateData.rate) * rateData.buyFeeRate,
        total: (previewAmount / rateData.rate) * (1 + rateData.buyFeeRate),
      }
    : null;
  const sellPreview = rateData && previewAmount > 0 && activeTab === 'sell'
    ? {
        basePayout: previewAmount / rateData.rate,
        fee: (previewAmount / rateData.rate) * rateData.sellFeeRate,
        net: (previewAmount / rateData.rate) * (1 - rateData.sellFeeRate),
      }
    : null;

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold flex items-center gap-3">
            <ArrowRightLeft size={28} className="text-white" /> Credit Exchange
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Credit Exchange. Buy fee {rateData ? `${rateData.buyFeeRate * 100}%` : '5%'}, sell fee {rateData ? `${rateData.sellFeeRate * 100}%` : '20%'}.
            {rateData ? ` Daily sell limit: ${rateData.dailySellLimit}cr` : ''}
          </p>
        </div>

        {/* Rate + Balance Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Current Rate</span>
              <TrendingUp size={20} className="text-white" />
            </div>
            {rateLoading ? (
              <div className="text-text-tertiary">Loading...</div>
            ) : rateData ? (
              <>
                <div className="text-2xl font-bold text-white">{rateData.rate} cr/$1</div>
                <div className="text-xs text-text-tertiary mt-1">1 credit = ${rateData.creditPrice}</div>
              </>
            ) : null}
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Your Balance</span>
              <Coins size={20} className="text-white" />
            </div>
            <div className="text-2xl font-bold text-white">{balance}</div>
            <div className="text-xs text-text-tertiary mt-1">credits available</div>
          </div>

          <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-text-secondary text-sm">Platform Fee</span>
              <DollarSign size={20} className="text-gray-300" />
            </div>
            <div className="text-2xl font-bold text-gray-300">
              {rateData ? `${rateData.buyFeeRate * 100}% / ${rateData.sellFeeRate * 100}%` : '5% / 20%'}
            </div>
            <div className="text-xs text-text-tertiary mt-1">Buy / Sell fee</div>
          </div>
        </div>

        {/* Exchange Form */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-6 mb-8">
          <h2 className="font-semibold mb-4">Exchange Credits</h2>

          {/* Buy/Sell Tabs */}
          <div className="flex gap-2 mb-6">
            <button
              onClick={() => { setActiveTab('buy'); setResult(null); setError(null); }}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                activeTab === 'buy'
                  ? 'bg-black/10 text-white border border-black/20'
                  : 'bg-bg-elevated text-text-secondary hover:text-text-primary'
              )}
            >
              <ArrowDownRight size={16} className="inline mr-1" /> Buy Credits
            </button>
            <button
              onClick={() => { setActiveTab('sell'); setResult(null); setError(null); }}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                activeTab === 'sell'
                  ? 'bg-black/10 text-white border border-black/20'
                  : 'bg-bg-elevated text-text-secondary hover:text-text-primary'
              )}
            >
              <ArrowUpRight size={16} className="inline mr-1" /> Sell Credits
            </button>
          </div>

          {/* Amount Input */}
          <div className="mb-4">
            <label className="text-sm text-text-secondary mb-2 block">
              {activeTab === 'buy' ? 'Credits to buy' : 'Credits to sell'}
            </label>
            <div className="flex gap-3">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={activeTab === 'buy' ? 'e.g. 100' : 'e.g. 50'}
                className="flex-1 bg-bg-elevated border border-border-primary rounded-lg px-4 py-3 text-lg focus:outline-none focus:border-black/40"
                min={1}
              />
              {activeTab === 'buy' ? (
                <button
                  onClick={handleStripeCheckout}
                  disabled={stripeLoading || !amount}
                  className={cn(
                    'px-6 py-3 rounded-lg font-medium transition-all flex items-center gap-2',
                    stripeLoading || !amount
                      ? 'bg-bg-elevated text-text-tertiary cursor-not-allowed'
                      : 'text-white'
                  )}
                  style={!stripeLoading && amount ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
                >
                  {stripeLoading ? <Loader2 size={16} className="animate-spin" /> : <CreditCard size={16} />}
                  Pay with Card
                </button>
              ) : (
                <button
                  onClick={handleExchange}
                  disabled={loading || !amount}
                  className={cn(
                    'px-6 py-3 rounded-lg font-medium transition-all flex items-center gap-2',
                    loading || !amount
                      ? 'bg-bg-elevated text-text-tertiary cursor-not-allowed'
                      : 'text-white'
                  )}
                  style={!loading && amount ? { background: 'linear-gradient(135deg, #f08535 0%, #c04510 100%)' } : undefined}
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRightLeft size={16} />}
                  Sell
                </button>
              )}
            </div>
          </div>

          {/* Bank Account Input (Sell only) */}
          {activeTab === 'sell' && (
            <div className="mb-4">
              <label className="text-sm text-text-secondary mb-2 block">
                Payout Bank Account
              </label>
              <input
                type="text"
                value={bankAccount}
                onChange={(e) => setBankAccount(e.target.value)}
                placeholder="Bank name / Account number"
                className="w-full bg-bg-elevated border border-border-primary rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-black/40"
              />
              <div className="mt-2 px-3 py-2 bg-black/[0.03] border border-white/[0.06] rounded-lg">
                <p className="text-[11px] text-text-tertiary leading-relaxed">
                  <strong className="text-text-secondary">Beta Notice:</strong> Real payouts are not available during closed beta.
                  Sell transactions are simulated. Use a virtual/test bank account.
                </p>
              </div>
            </div>
          )}

          {/* Quick amounts */}
          <div className="flex gap-2 mb-4">
            {[10, 50, 100, 500, 1000].map((qty) => (
              <button
                key={qty}
                onClick={() => setAmount(String(qty))}
                className="px-3 py-1.5 bg-bg-elevated border border-border-primary rounded-lg text-sm text-text-secondary hover:text-text-primary hover:border-black/20 transition-all"
              >
                {qty}
              </button>
            ))}
          </div>

          {/* Preview */}
          {(buyPreview || sellPreview) && rateData && (
            <div className="bg-bg-elevated rounded-lg p-4 border border-border-primary">
              <div className="flex items-center gap-2 mb-2 text-sm text-text-secondary">
                <Info size={14} /> Preview
              </div>
              {buyPreview ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Credits</span>
                    <span className="text-gray-300 font-medium">+{previewAmount} credits</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Base cost</span>
                    <span>${buyPreview.baseCost.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Fee ({rateData.buyFeeRate * 100}%)</span>
                    <span className="text-gray-400">${buyPreview.fee.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between border-t border-border-primary pt-1 font-medium">
                    <span>Total</span>
                    <span>${buyPreview.total.toFixed(2)}</span>
                  </div>
                </div>
              ) : sellPreview ? (
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Credits</span>
                    <span className="text-gray-500 font-medium">-{previewAmount} credits</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Gross payout</span>
                    <span>${sellPreview.basePayout.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Fee ({rateData.sellFeeRate * 100}%)</span>
                    <span className="text-gray-400">-${sellPreview.fee.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between border-t border-border-primary pt-1 font-medium">
                    <span>You receive</span>
                    <span className="text-gray-300">${sellPreview.net.toFixed(2)}</span>
                  </div>
                </div>
              ) : null}
            </div>
          )}

          {/* Result */}
          {result && (
            <div className="mt-4 bg-black/5 border border-black/10 rounded-lg px-4 py-3 text-gray-300 text-sm">
              {activeTab === 'buy'
                ? `Successfully bought ${result.creditsReceived} credits for $${result.moneyPaid} (fee: $${result.fee})`
                : `Successfully sold ${result.creditsSold} credits for $${result.moneyReceived} (fee: $${result.fee})`}
              <div className="text-xs text-gray-400 mt-1">New balance: {result.newBalance} credits</div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-4 bg-black/5 border border-black/10 rounded-lg px-4 py-3 text-gray-400 text-sm">
              {error}
            </div>
          )}
        </div>

        {/* Exchange History */}
        <div className="bg-bg-secondary border border-border-primary rounded-xl p-5">
          <h2 className="font-semibold mb-3 flex items-center gap-2">
            <Clock size={16} /> Exchange History
          </h2>
          {history.length === 0 ? (
            <div className="text-center text-text-tertiary py-8">
              No exchanges yet. Buy or sell credits to get started!
            </div>
          ) : (
            <div className="space-y-2">
              {history.map((ex) => (
                <div key={ex.id} className="flex items-center justify-between py-2 border-b border-border-primary last:border-0">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'w-8 h-8 rounded-lg flex items-center justify-center',
                      ex.type === 'BUY' ? 'bg-black/5' : 'bg-black/5'
                    )}>
                      {ex.type === 'BUY'
                        ? <ArrowDownRight size={16} className="text-gray-300" />
                        : <ArrowUpRight size={16} className="text-gray-500" />}
                    </div>
                    <div>
                      <p className="text-sm font-medium">
                        {ex.type === 'BUY' ? 'Bought' : 'Sold'} {ex.creditAmount} credits
                      </p>
                      <p className="text-xs text-text-tertiary">{formatTime(ex.createdAt)}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={cn(
                      'text-sm font-semibold',
                      ex.type === 'BUY' ? 'text-gray-300' : 'text-gray-500'
                    )}>
                      {ex.type === 'BUY' ? `-$${ex.netMoney}` : `+$${ex.netMoney}`}
                    </span>
                    <p className="text-xs text-text-tertiary">fee: ${ex.fee}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Credit Payment Modal */}
      <CreditPaymentModal
        isOpen={showPaymentModal}
        onClose={() => { setShowPaymentModal(false); setPaymentCreditAmount(0); }}
        creditAmount={paymentCreditAmount}
        onSuccess={handlePaymentSuccess}
      />
    </div>
  );
}
