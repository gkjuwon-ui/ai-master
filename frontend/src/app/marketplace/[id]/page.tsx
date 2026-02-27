'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import {
  Star, Download, Shield, ArrowLeft, ShoppingCart, Play,
  Check, Clock, User, Calendar, Tag, Monitor, Code2,
  ChevronDown, ChevronUp, ExternalLink, MessageSquare, Coins
} from 'lucide-react';
import { useAgentStore } from '@/store/agentStore';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/common/Button';
import { Loading } from '@/components/common/Loading';
import { formatPrice, formatDate, formatNumber, getCategoryLabel } from '@/lib/utils';
import { api } from '@/lib/api';
import toast from 'react-hot-toast';

export default function AgentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.id as string;
  const { currentAgent, isLoading, fetchAgentBySlug } = useAgentStore();
  const { user, isAuthenticated } = useAuthStore();

  const [activeTab, setActiveTab] = useState<'overview' | 'reviews' | 'versions'>('overview');
  const [reviews, setReviews] = useState<any[]>([]);
  const [versions, setVersions] = useState<any[]>([]);
  const [hasAccess, setHasAccess] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [showFullDesc, setShowFullDesc] = useState(false);
  const [reviewText, setReviewText] = useState('');
  const [reviewRating, setReviewRating] = useState(5);
  const [submittingReview, setSubmittingReview] = useState(false);
  const [creditCost, setCreditCost] = useState<number | null>(null);
  const [userCredits, setUserCredits] = useState<number>(0);
  const [exchangeRate, setExchangeRate] = useState<number>(10);

  useEffect(() => {
    fetchAgentBySlug(slug);
  }, [slug, fetchAgentBySlug]);

  useEffect(() => {
    if (currentAgent) {
      // Load reviews for everyone
      api.agents.getReviews(currentAgent.id).then(r => setReviews(r?.reviews || r || [])).catch(() => {});
      // Check access and credit info when authenticated
      if (isAuthenticated) {
        api.agents.checkAccess(currentAgent.id).then(r => setHasAccess(r?.hasAccess || false)).catch(() => {});
        api.credits.getBalance().then(r => setUserCredits(r?.credits ?? r?.balance ?? 0)).catch(() => {});
      }
      // Dynamic credit cost: fetch exchange rate and multiply by dollar price
      api.exchange.getRate().then((r: any) => {
        const rate = r?.rate ?? 10;
        setExchangeRate(rate);
        if (currentAgent.price === 0 || currentAgent.tier === 'F') {
          setCreditCost(0);
        } else {
          setCreditCost(Math.max(1, Math.round(currentAgent.price * rate)));
        }
      }).catch(() => {
        // Fallback: use base rate
        setCreditCost(currentAgent.price === 0 ? 0 : Math.max(1, Math.round(currentAgent.price * 10)));
      });
    }
  }, [currentAgent, isAuthenticated]);

  const handlePurchase = async () => {
    if (!isAuthenticated) { router.push('/auth/login'); return; }
    if (!currentAgent) return;
    setPurchasing(true);
    try {
      await api.credits.purchase(currentAgent.id);
      setHasAccess(true);
      // Refresh credit balance
      api.credits.getBalance().then(r => setUserCredits(r?.credits ?? 0)).catch(() => {});
      toast.success(`You now have access to ${currentAgent.name}!`);
    } catch (err: any) {
      toast.error(err.message || 'Purchase failed — not enough credits?');
    } finally {
      setPurchasing(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!currentAgent || !reviewText.trim()) return;
    setSubmittingReview(true);
    try {
      await api.agents.addReview(currentAgent.id, { rating: reviewRating, title: reviewText.slice(0, 50) || 'Review', content: reviewText });
      toast.success('Review submitted');
      setReviewText('');
      const r = await api.agents.getReviews(currentAgent.id);
      setReviews(r?.reviews || r || []);
    } catch (err: any) {
      toast.error(err.message || 'Failed to submit review');
    } finally {
      setSubmittingReview(false);
    }
  };

  if (isLoading || !currentAgent) {
    return <Loading />;
  }

  const agent = currentAgent;
  const isFree = (creditCost ?? 0) === 0;
  const canUse = hasAccess;

  return (
    <div className="max-w-6xl mx-auto">
      {/* Back */}
      <Link
        href="/marketplace"
        className="inline-flex items-center gap-2 text-sm text-text-tertiary hover:text-text-primary transition-colors mb-6"
      >
        <ArrowLeft size={16} />
        Back to Marketplace
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Hero */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="card overflow-hidden"
          >
            {/* Thumbnail */}
            <div className="aspect-video bg-bg-elevated relative">
              {agent.thumbnailUrl ? (
                <img src={agent.thumbnailUrl} alt={agent.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-bg-secondary to-bg-tertiary">
                  <Code2 size={64} className="text-text-tertiary" />
                </div>
              )}
              {agent.verified && (
                <div className="absolute top-4 left-4 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/20 text-accent border border-accent/30 text-xs font-medium">
                  <Shield size={12} />
                  Verified Agent
                </div>
              )}
            </div>

            <div className="p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h1 className="text-2xl font-bold mb-1">{agent.name}</h1>
                  <div className="flex items-center gap-3 text-sm text-text-secondary">
                    <span className="flex items-center gap-1">
                      <User size={14} />
                      {agent.developer?.displayName || agent.developer?.name || 'Unknown'}
                    </span>
                    <span className="flex items-center gap-1">
                      <Tag size={14} />
                      {getCategoryLabel(agent.category)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar size={14} />
                      {formatDate(agent.createdAt)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-6 mb-6">
                <div className="flex items-center gap-1.5">
                  <Star size={16} className="text-warning fill-warning" />
                  <span className="font-semibold">{agent.rating?.toFixed(1) || '0.0'}</span>
                  <span className="text-text-tertiary text-sm">({agent.reviewCount || 0} reviews)</span>
                </div>
                <div className="flex items-center gap-1.5 text-text-secondary">
                  <Download size={16} />
                  <span className="text-sm">{formatNumber(agent.stats?.downloads || agent.downloadCount || 0)} downloads</span>
                </div>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 border-b border-border-primary mb-6">
                {(['overview', 'reviews', 'versions'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-2 text-sm font-medium transition-all border-b-2 -mb-px capitalize ${
                      activeTab === tab
                        ? 'text-white border-white'
                        : 'text-text-tertiary border-transparent hover:text-text-secondary'
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Description */}
                  <div>
                    <h3 className="text-sm font-semibold mb-3 text-text-secondary uppercase tracking-wider">Description</h3>
                    <div className={`prose prose-invert prose-sm max-w-none ${!showFullDesc && 'line-clamp-6'}`}>
                      <p className="text-text-secondary leading-relaxed whitespace-pre-wrap">
                        {agent.description}
                      </p>
                    </div>
                    {agent.description.length > 400 && (
                      <button
                        onClick={() => setShowFullDesc(!showFullDesc)}
                        className="flex items-center gap-1 mt-2 text-xs text-text-tertiary hover:text-text-primary transition-colors"
                      >
                        {showFullDesc ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        {showFullDesc ? 'Show less' : 'Read more'}
                      </button>
                    )}
                  </div>

                  {/* Capabilities */}
                  {agent.capabilities && agent.capabilities.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3 text-text-secondary uppercase tracking-wider">Capabilities</h3>
                      <div className="flex flex-wrap gap-2">
                        {agent.capabilities.map((cap: string) => (
                          <span key={cap} className="px-3 py-1.5 rounded-lg text-xs bg-bg-elevated text-text-secondary border border-border-primary">
                            <Monitor size={10} className="inline mr-1.5" />
                            {cap.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tags */}
                  {agent.tags && agent.tags.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold mb-3 text-text-secondary uppercase tracking-wider">Tags</h3>
                      <div className="flex flex-wrap gap-2">
                        {agent.tags.map((tag: string) => (
                          <span key={tag} className="px-2.5 py-1 rounded-md text-xs text-text-tertiary bg-bg-secondary border border-border-primary">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'reviews' && (
                <div className="space-y-6">
                  {/* Write review */}
                  {canUse && isAuthenticated && (
                    <div className="card p-4 space-y-3">
                      <h4 className="text-sm font-semibold">Write a Review</h4>
                      <div className="flex items-center gap-1">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <button key={s} onClick={() => setReviewRating(s)}>
                            <Star
                              size={20}
                              className={s <= reviewRating ? 'text-warning fill-warning' : 'text-text-tertiary'}
                            />
                          </button>
                        ))}
                      </div>
                      <textarea
                        value={reviewText}
                        onChange={(e) => setReviewText(e.target.value)}
                        placeholder="Share your experience with this agent..."
                        className="input-field w-full h-24 resize-none"
                      />
                      <Button
                        size="sm"
                        onClick={handleSubmitReview}
                        loading={submittingReview}
                        disabled={!reviewText.trim()}
                      >
                        Submit Review
                      </Button>
                    </div>
                  )}

                  {/* Reviews list */}
                  {reviews.length === 0 ? (
                    <p className="text-text-tertiary text-sm text-center py-8">No reviews yet. Be the first!</p>
                  ) : (
                    <div className="space-y-4">
                      {reviews.map((review) => (
                        <div key={review.id} className="card p-4 space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <div className="w-6 h-6 rounded-full bg-bg-elevated flex items-center justify-center text-[10px] font-bold text-text-tertiary">
                                {(review.user?.displayName || review.user?.name)?.[0]?.toUpperCase() || '?'}
                              </div>
                              <span className="text-sm font-medium">{review.user?.displayName || review.user?.name || 'Anonymous'}</span>
                              <div className="flex items-center gap-0.5">
                                {Array.from({ length: 5 }).map((_, i) => (
                                  <Star
                                    key={i}
                                    size={10}
                                    className={i < review.rating ? 'text-warning fill-warning' : 'text-border-primary'}
                                  />
                                ))}
                              </div>
                            </div>
                            <span className="text-[11px] text-text-tertiary">
                              {formatDate(review.createdAt)}
                            </span>
                          </div>
                          <p className="text-sm text-text-secondary">{review.content || review.comment}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'versions' && (
                <div className="space-y-3">
                  {/* Current version */}
                  <div className="card p-4 border-accent/20">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">v{agent.version || '1.0.0'}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent">Current</span>
                      </div>
                      <span className="text-xs text-text-tertiary">{formatDate(agent.updatedAt || agent.createdAt)}</span>
                    </div>
                  </div>

                  {/* Version history */}
                  {versions.length > 0 ? (
                    versions
                      .filter((v: any) => v.version !== agent.version)
                      .map((v: any) => (
                        <div key={v.id} className="card p-4">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium">v{v.version}</span>
                            <span className="text-xs text-text-tertiary">{formatDate(v.createdAt)}</span>
                          </div>
                          {v.changelog && (
                            <p className="text-xs text-text-secondary mt-1">{v.changelog}</p>
                          )}
                        </div>
                      ))
                  ) : (
                    <p className="text-xs text-text-tertiary text-center py-4">This is the initial release</p>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Purchase / Use card */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 }}
            className="card p-6 space-y-4 sticky top-6"
          >
            <div className="text-center">
              <div className="text-3xl font-bold mb-1 flex items-center justify-center gap-2">
                {isFree ? 'Free' : <><span className="text-lg text-text-secondary">${agent.price}</span> <Coins size={22} className="text-white" /> {creditCost} Credits</>}
              </div>
              <div className="text-xs text-text-tertiary mt-1">
                {isFree ? 'Free Agent' : `Rate: ${exchangeRate} cr/$1`}
              </div>
            </div>

            {canUse ? (
              <div className="space-y-3">
                <Link href={`/workspace?agents=${agent.id}`} className="block">
                  <Button className="w-full" size="lg" icon={<Play size={16} />}>
                    Run Agent
                  </Button>
                </Link>
                <div className="flex items-center justify-center gap-1.5 text-xs text-success">
                  <Check size={14} />
                  {isFree ? 'Free to use' : 'Purchased'}
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <Button
                  className="w-full"
                  size="lg"
                  icon={<ShoppingCart size={16} />}
                  onClick={handlePurchase}
                  loading={purchasing}
                  disabled={purchasing}
                >
                  {isFree ? 'Get for Free' : `Purchase (${creditCost} Credits)`}
                </Button>
                {isAuthenticated && (
                  <p className="text-[11px] text-text-tertiary text-center">
                    Your balance: {userCredits} credits
                  </p>
                )}
              </div>
            )}

            <div className="border-t border-border-primary pt-4 space-y-3">
              <InfoRow label="Category" value={getCategoryLabel(agent.category)} />
              <InfoRow label="Version" value={agent.version || '1.0.0'} />
              <InfoRow label="Rating" value={`${(agent.rating ?? agent.stats?.rating ?? 0).toFixed(1)} / 5.0`} />
              <InfoRow label="Downloads" value={formatNumber(agent.stats?.downloads || agent.downloadCount || 0)} />
              <InfoRow label="Updated" value={formatDate(agent.updatedAt || agent.createdAt)} />
              <InfoRow label="License" value="Standard" />
            </div>
          </motion.div>

          {/* Developer info card */}
          {agent.developer && (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
              className="card p-5 space-y-4 sticky top-96"
            >
              <h4 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">Developer</h4>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-bg-elevated flex items-center justify-center text-sm font-bold text-text-tertiary">
                  {(agent.developer.displayName || agent.developer.name)?.[0]?.toUpperCase() || '?'}
                </div>
                <div>
                  <div className="font-medium text-sm">{agent.developer.displayName || agent.developer.name}</div>
                  <div className="text-xs text-text-tertiary">
                    {agent.developer.agentCount || 0} agents published
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-text-tertiary">{label}</span>
      <span className="text-text-secondary">{value}</span>
    </div>
  );
}
