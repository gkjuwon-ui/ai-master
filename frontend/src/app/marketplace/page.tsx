'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Package } from 'lucide-react';
import { useAgentStore } from '@/store/agentStore';
import { AgentCard, AgentCardSkeleton } from '@/components/marketplace/AgentCard';
import { SearchBar, CategoryFilter, SortSelect, PricingFilter } from '@/components/marketplace/SearchFilters';
import { EmptyState } from '@/components/common/Loading';
import { getCategoryLabel } from '@/lib/utils';

const CATEGORIES = [
  'CODING', 'DESIGN', 'RESEARCH', 'DATA_ANALYSIS', 'WRITING',
  'AUTOMATION', 'PRODUCTIVITY', 'COMMUNICATION', 'MEDIA',
  'MONITORING', 'SYSTEM', 'OTHER',
].map(c => ({ value: c, label: getCategoryLabel(c) }));

export default function MarketplacePage() {
  return (
    <Suspense fallback={<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">{Array.from({ length: 8 }).map((_, i) => <AgentCardSkeleton key={i} />)}</div>}>
      <MarketplaceContent />
    </Suspense>
  );
}

function MarketplaceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { agents, totalAgents, isLoading, fetchAgents, filters, setFilter } = useAgentStore();

  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [sortBy, setSortBy] = useState(searchParams.get('sort') || 'popular');
  const [category, setCategory] = useState(searchParams.get('category') || '');
  const [pricing, setPricing] = useState(searchParams.get('pricing') || '');
  const [page, setPage] = useState(1);

  const doFetch = useCallback(() => {
    const query: Record<string, any> = {
      page,
      limit: 12,
      sortBy,
    };
    if (search) query.search = search;
    if (category) query.category = category;
    if (pricing) query.pricing = pricing;
    fetchAgents(query);
  }, [fetchAgents, page, sortBy, search, category, pricing]);

  useEffect(() => {
    doFetch();
  }, [doFetch]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (category) params.set('category', category);
    if (sortBy !== 'popular') params.set('sort', sortBy);
    if (pricing) params.set('pricing', pricing);
    const qs = params.toString();
    router.replace(`/marketplace${qs ? `?${qs}` : ''}`, { scroll: false });
  }, [search, category, sortBy, pricing, router]);

  const handleSearch = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  const handleCategory = (val: string) => {
    setCategory(val);
    setPage(1);
  };

  const handleSort = (val: string) => {
    setSortBy(val);
    setPage(1);
  };

  const handlePricing = (val: string) => {
    setPricing(val);
    setPage(1);
  };

  const totalPages = Math.ceil(totalAgents / 12);

  return (
    <div className="max-w-7xl mx-auto space-y-6 px-6 py-12">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold mb-2">Agent Marketplace</h1>
        <p className="text-text-secondary">
          Discover OS-controlling AI agents built by developers worldwide
        </p>
        <p className="text-text-tertiary text-xs mt-1.5">
          Agents learn from each other&apos;s executions and get smarter over time &mdash; unlike static AI tools.
        </p>
      </div>

      {/* Search */}
      <div data-tour="mp-search"><SearchBar value={search} onChange={handleSearch} onSubmit={doFetch} /></div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
        <CategoryFilter
          categories={CATEGORIES}
          selected={category}
          onChange={handleCategory}
        />
        <div className="flex items-center gap-3 flex-shrink-0 h-9">
          <PricingFilter value={pricing} onChange={handlePricing} />
          <SortSelect value={sortBy} onChange={handleSort} />
        </div>
      </div>

      {/* Results count */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-tertiary">
          {isLoading ? 'Loading...' : `${totalAgents} agent${totalAgents !== 1 ? 's' : ''} found`}
        </p>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <AgentCardSkeleton key={i} />
          ))}
        </div>
      ) : agents.length === 0 ? (
        <EmptyState
          icon={<Package size={48} />}
          title="No agents found"
          description={search ? `No results for "${search}". Try different keywords.` : 'No agents match the current filters.'}
          action={{
            label: 'Clear filters',
            onClick: () => {
              setSearch('');
              setCategory('');
              setPricing('');
              setSortBy('popular');
            },
          }}
        />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {agents.map((agent, i) => (
              <AgentCard key={agent.id} agent={agent} index={i} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-6">
              <button
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                className="px-4 py-2 text-sm rounded-lg border border-border-primary text-text-secondary hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                Previous
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                  let pageNum: number;
                  if (totalPages <= 7) {
                    pageNum = i + 1;
                  } else if (page <= 4) {
                    pageNum = i + 1;
                  } else if (page >= totalPages - 3) {
                    pageNum = totalPages - 6 + i;
                  } else {
                    pageNum = page - 3 + i;
                  }
                  return (
                    <button
                      key={pageNum}
                      onClick={() => setPage(pageNum)}
                      className={`w-8 h-8 rounded-lg text-xs font-medium transition-all ${
                        page === pageNum
                          ? 'bg-accent text-white'
                          : 'text-text-secondary hover:text-text-primary hover:bg-bg-elevated'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>
              <button
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                className="px-4 py-2 text-sm rounded-lg border border-border-primary text-text-secondary hover:text-text-primary hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
