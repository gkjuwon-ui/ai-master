'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { ShoppingCart, CheckCircle2, ArrowLeft, Coins } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';
import { api } from '@/lib/api';
import Link from 'next/link';
import toast from 'react-hot-toast';

export default function CheckoutPage() {
  const params = useParams();
  const router = useRouter();
  const agentId = params.id as string;

  const [agent, setAgent] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [success, setSuccess] = useState(false);
  const [balance, setBalance] = useState(0);
  const [creditCost, setCreditCost] = useState(0);

  useEffect(() => {
    const init = async () => {
      try {
        const [agentRes, balanceRes, rateRes] = await Promise.all([
          api.agents.getById(agentId),
          api.credits.getBalance(),
          api.exchange.getRate(),
        ]);
        setAgent(agentRes);
        setBalance(balanceRes?.credits ?? 0);
        const rate = rateRes?.rate ?? 10;
        if (agentRes.price === 0 || agentRes.tier === 'F') {
          setCreditCost(0);
        } else {
          setCreditCost(Math.max(1, Math.round(agentRes.price * rate)));
        }
      } catch {
        toast.error('Agent not found');
        router.push('/marketplace');
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [agentId, router]);

  const handlePurchase = async () => {
    setProcessing(true);
    try {
      await api.credits.purchase(agentId);
      setSuccess(true);
      toast.success('Purchase complete!');
    } catch (err: any) {
      toast.error(err.message || 'Not enough credits');
    } finally {
      setProcessing(false);
    }
  };

  if (loading) return <Loading />;
  if (!agent) return null;

  if (success) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center">
        <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200, damping: 20 }}>
          <CheckCircle2 size={64} className="text-success mx-auto mb-6" />
        </motion.div>
        <h1 className="text-2xl font-bold mb-2">Purchase Complete!</h1>
        <p className="text-text-secondary mb-6">
          You now have access to <span className="font-semibold text-text-primary">{agent.name}</span>.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link href={`/workspace?agents=${agentId}`}>
            <Button icon={<ShoppingCart size={16} />}>Run Agent</Button>
          </Link>
          <Link href="/dashboard">
            <Button variant="secondary">Dashboard</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto mt-10 space-y-6">
      <Link href={`/marketplace/${agent.slug || agentId}`} className="inline-flex items-center gap-2 text-sm text-text-tertiary hover:text-text-primary transition-colors">
        <ArrowLeft size={16} />
        Back to agent
      </Link>

      <div className="card p-6 space-y-6">
        <h1 className="text-xl font-bold">Purchase with Credits</h1>

        <div className="flex items-center gap-4 p-4 bg-bg-secondary rounded-xl">
          <div className="w-14 h-14 rounded-xl bg-bg-elevated flex items-center justify-center text-text-tertiary">
            <ShoppingCart size={24} />
          </div>
          <div className="flex-1">
            <div className="font-semibold">{agent.name}</div>
            <div className="text-sm text-text-secondary">Tier {agent.tier || 'F'} • {agent.category}</div>
          </div>
          <div className="text-xl font-bold flex items-center gap-1">
            <Coins size={18} className="text-white" />
            {creditCost}
          </div>
        </div>

        <div className="space-y-3 border-t border-border-primary pt-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">Agent cost</span>
            <span>{creditCost} credits</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-secondary">Your balance</span>
            <span className={balance < creditCost ? 'text-error' : 'text-success'}>{balance} credits</span>
          </div>
          <div className="flex items-center justify-between text-sm border-t border-border-primary pt-3">
            <span className="font-semibold">After purchase</span>
            <span className="font-bold text-lg">{balance - creditCost} credits</span>
          </div>
        </div>

        <Button
          className="w-full"
          size="lg"
          onClick={handlePurchase}
          loading={processing}
          disabled={balance < creditCost}
          icon={<Coins size={16} />}
        >
          {balance < creditCost ? 'Not Enough Credits' : creditCost === 0 ? 'Get for Free' : `Purchase (${creditCost} Credits)`}
        </Button>

        {balance < creditCost && (
          <p className="text-xs text-center text-text-tertiary">
            Earn more credits by posting in the <Link href="/community" className="text-accent hover:underline">Community</Link>.
          </p>
        )}
      </div>
    </div>
  );
}
