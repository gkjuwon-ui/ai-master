// Determine API URL dynamically for Electron environment
function getApiUrl(): string {
  if (typeof window !== 'undefined') {
    // Electron — use localhost with configured port
    if ((window as any).electronAPI) {
      return 'http://localhost:4000';
    }
  }
  // Otherwise use env var or default
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:4000';
}

// Detect platform
function getPlatform(): 'desktop' | 'web' {
  if (typeof window === 'undefined') return 'web';
  if ((window as any).electronAPI) return 'desktop';
  return 'web';
}

export const currentPlatform = getPlatform();

const API_URL = getApiUrl();

interface RequestOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
  rawBody?: boolean;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('accessToken');
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {}, rawBody = false } = options;
    const token = this.getToken();

    const requestHeaders: Record<string, string> = {
      ...headers,
    };

    if (token) {
      requestHeaders['Authorization'] = `Bearer ${token}`;
    }

    if (body && !rawBody) {
      requestHeaders['Content-Type'] = 'application/json';
    }

    const config: RequestInit = {
      method,
      headers: requestHeaders,
    };

    if (body) {
      config.body = rawBody ? body : JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, config);

    // Handle token refresh (skip for auth endpoints — they return 401 for invalid credentials)
    if (response.status === 401 && !endpoint.startsWith('/api/auth/login') && !endpoint.startsWith('/api/auth/register')) {
      const refreshed = await this.refreshToken();
      if (refreshed) {
        requestHeaders['Authorization'] = `Bearer ${this.getToken()}`;
        const retryResponse = await fetch(`${this.baseUrl}${endpoint}`, {
          ...config,
          headers: requestHeaders,
        });
        if (!retryResponse.ok) {
          const error = await retryResponse.json().catch(() => ({}));
          throw new ApiError(error.error?.message || 'Request failed', retryResponse.status, error.error?.code);
        }
        const retryJson = await retryResponse.json();
        if (retryJson && typeof retryJson === 'object' && 'success' in retryJson && 'data' in retryJson) {
          return retryJson.data;
        }
        return retryJson;
      }

      // Refresh failed — clear tokens and let the UI handle redirect
      if (typeof window !== 'undefined') {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        // Dispatch a custom event so authStore can react without full page reload
        window.dispatchEvent(new CustomEvent('auth:session-expired'));
      }
      throw new ApiError('Session expired', 401, 'SESSION_EXPIRED');
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new ApiError(
        errorBody.error?.message || `Request failed with status ${response.status}`,
        response.status,
        errorBody.error?.code || 'UNKNOWN_ERROR',
        errorBody
      );
    }

    const json = await response.json();
    // Auto-unwrap { success, data } envelope so callers always get the payload directly
    if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
      return json.data;
    }
    return json;
  }

  private async refreshToken(): Promise<boolean> {
    try {
      const refreshToken = localStorage.getItem('refreshToken');
      if (!refreshToken) return false;

      const response = await fetch(`${this.baseUrl}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      });

      if (!response.ok) return false;

      const data = await response.json();
      if (data.success && data.data) {
        localStorage.setItem('accessToken', data.data.accessToken);
        localStorage.setItem('refreshToken', data.data.refreshToken);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  // ── Generic HTTP helpers ──────────────────────────────
  get<T = any>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint);
  }
  post<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'POST', body });
  }
  put<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'PUT', body });
  }
  patch<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'PATCH', body });
  }
  delete<T = any>(endpoint: string, body?: any): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE', body });
  }

  // Auth
  async login(email: string, password: string) {
    return this.request<any>('/api/auth/login', { method: 'POST', body: { email, password } });
  }

  async register(data: { email: string; username: string; password: string; displayName: string }) {
    return this.request<any>('/api/auth/register', { method: 'POST', body: data });
  }

  async verifyEmail(email: string, code: string) {
    return this.request<any>('/api/auth/verify-email', { method: 'POST', body: { email, code } });
  }

  async resendVerification(email: string) {
    return this.request<any>('/api/auth/resend-verification', { method: 'POST', body: { email } });
  }

  async getMe() {
    return this.request<any>('/api/auth/me');
  }

  async updateProfile(data: any) {
    return this.request<any>('/api/auth/profile', { method: 'PUT', body: data });
  }

  async upgradeToDeveloper() {
    return this.request<any>('/api/auth/upgrade-developer', { method: 'POST' });
  }

  async logout() {
    const refreshToken = localStorage.getItem('refreshToken');
    return this.request<any>('/api/auth/logout', { method: 'POST', body: { refreshToken } });
  }

  // Agents
  async getAgents(params?: Record<string, any>) {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return this.request<any>(`/api/agents${query}`);
  }

  async getAgent(id: string) {
    return this.request<any>(`/api/agents/${id}`);
  }

  async getAgentBySlug(slug: string) {
    return this.request<any>(`/api/agents/slug/${slug}`);
  }

  async getPurchasedAgents() {
    return this.request<any>('/api/agents/purchased');
  }

  async getMyAgents() {
    return this.request<any>('/api/agents/my');
  }

  async createAgent(data: any) {
    return this.request<any>('/api/agents', { method: 'POST', body: data });
  }

  async updateAgent(id: string, data: any) {
    return this.request<any>(`/api/agents/${id}`, { method: 'PUT', body: data });
  }

  async publishAgent(id: string) {
    return this.request<any>(`/api/agents/${id}/publish`, { method: 'POST' });
  }

  async unpublishAgent(id: string) {
    return this.request<any>(`/api/agents/${id}/unpublish`, { method: 'POST' });
  }

  async deleteAgent(id: string) {
    return this.request<any>(`/api/agents/${id}`, { method: 'DELETE' });
  }

  async uploadAgentBundle(agentId: string, file: File) {
    const formData = new FormData();
    formData.append('bundle', file);
    return this.request<any>(`/api/developer/agents/${agentId}/upload`, {
      method: 'POST',
      body: formData,
      rawBody: true,
    });
  }

  async checkAgentAccess(id: string) {
    return this.request<any>(`/api/agents/${id}/access`);
  }

  async addReview(agentId: string, data: { rating: number; title: string; content: string }) {
    return this.request<any>(`/api/agents/${agentId}/reviews`, { method: 'POST', body: data });
  }

  async getReviews(agentId: string, page = 1) {
    return this.request<any>(`/api/agents/${agentId}/reviews?page=${page}`);
  }

  // Agent LLM Assignment (Multi-brain)
  async assignAgentLLM(agentId: string, llmConfigId: string | null) {
    return this.request<any>(`/api/agents/${agentId}/llm-config`, {
      method: 'PUT',
      body: { llmConfigId },
    });
  }

  async getAgentLLMConfig(agentId: string) {
    return this.request<any>(`/api/agents/${agentId}/llm-config`);
  }

  async getAllLLMAssignments() {
    return this.request<any>('/api/agents/all/llm-assignments');
  }

  // Agent Persona
  async getAgentPersona(agentId: string) {
    return this.request<{ persona: string | null }>(`/api/agents/${agentId}/persona`);
  }

  async saveAgentPersona(agentId: string, persona: string) {
    return this.request<any>(`/api/agents/${agentId}/persona`, {
      method: 'PUT',
      body: { persona },
    });
  }

  // Execution
  async checkCapabilities(data: { prompt: string; agentIds: string[] }) {
    return this.request<any>('/api/execution/check-capabilities', { method: 'POST', body: data });
  }

  async createExecution(data: any) {
    return this.request<any>('/api/execution', { method: 'POST', body: data });
  }

  async getExecutions(page = 1) {
    return this.request<any>(`/api/execution?page=${page}`);
  }

  async getExecution(id: string) {
    return this.request<any>(`/api/execution/${id}`);
  }

  async startExecution(id: string) {
    return this.request<any>(`/api/execution/${id}/start`, { method: 'POST' });
  }

  async pauseExecution(id: string) {
    return this.request<any>(`/api/execution/${id}/pause`, { method: 'POST' });
  }

  async cancelExecution(id: string) {
    return this.request<any>(`/api/execution/${id}/cancel`, { method: 'POST' });
  }

  async getExecutionLogs(id: string, after?: string) {
    const query = after ? `?after=${after}` : '';
    return this.request<any>(`/api/execution/${id}/logs${query}`);
  }

  async deleteExecution(id: string) {
    return this.request<any>(`/api/execution/${id}`, { method: 'DELETE' });
  }

  // Credits (replaces Payments)
  async getCreditBalance() {
    return this.request<any>('/api/credits/balance');
  }

  async getCreditSummary() {
    return this.request<any>('/api/credits/summary');
  }

  async getCreditLedger(page = 1) {
    return this.request<any>(`/api/credits/ledger?page=${page}`);
  }

  async purchaseWithCredits(agentId: string) {
    return this.request<any>('/api/credits/purchase', { method: 'POST', body: { agentId } });
  }

  // Legacy compat — claim free agent via credits (cost = 0)
  async claimFreeAgent(agentId: string) {
    return this.request<any>('/api/credits/purchase', { method: 'POST', body: { agentId } });
  }

  // Settings
  async getSettings() {
    return this.request<any>('/api/settings');
  }

  async updateSettings(data: any) {
    return this.request<any>('/api/settings', { method: 'PUT', body: data });
  }

  // LLM
  async getLLMProviders() {
    return this.request<any>('/api/settings/llm/providers');
  }

  async getLLMConfigs() {
    return this.request<any>('/api/settings/llm/configs');
  }

  async createLLMConfig(data: any) {
    return this.request<any>('/api/settings/llm/configs', { method: 'POST', body: data });
  }

  async updateLLMConfig(id: string, data: any) {
    return this.request<any>(`/api/settings/llm/configs/${id}`, { method: 'PUT', body: data });
  }

  async deleteLLMConfig(id: string) {
    return this.request<any>(`/api/settings/llm/configs/${id}`, { method: 'DELETE' });
  }

  async testLLMConfig(id: string) {
    return this.request<any>(`/api/settings/llm/configs/${id}/test`, { method: 'POST' });
  }

  // Notifications
  async getNotifications(page = 1) {
    return this.request<any>(`/api/settings/notifications?page=${page}`);
  }

  async markNotificationRead(id: string) {
    return this.request<any>(`/api/settings/notifications/${id}/read`, { method: 'PUT' });
  }

  async markAllNotificationsRead() {
    return this.request<any>('/api/settings/notifications/read-all', { method: 'POST' });
  }

  // Developer
  async getDeveloperStats() {
    return this.request<any>('/api/developer/stats');
  }

  async getDeveloperAgents() {
    return this.request<any>('/api/developer/agents');
  }

  async getApiKeys() {
    return this.request<any>('/api/developer/api-keys');
  }

  async createApiKey(data: any) {
    return this.request<any>('/api/developer/api-keys', { method: 'POST', body: data });
  }

  async deleteApiKey(id: string) {
    return this.request<any>(`/api/developer/api-keys/${id}`, { method: 'DELETE' });
  }

  async getDeveloperEarnings() {
    return this.request<any>('/api/developer/earnings');
  }

  // ── Namespaced proxies (used by page components) ────────────────────

  agents = {
    getById: (id: string) => this.getAgent(id),
    getBySlug: (slug: string) => this.getAgentBySlug(slug),
    create: (data: any) => this.createAgent(data),
    update: (id: string, data: any) => this.updateAgent(id, data),
    publish: (id: string) => this.publishAgent(id),
    unpublish: (id: string) => this.unpublishAgent(id),
    delete: (id: string) => this.deleteAgent(id),
    checkAccess: (id: string) => this.checkAgentAccess(id),
    addReview: (agentId: string, data: any) => this.addReview(agentId, data),
    getReviews: (agentId: string, page?: number) => this.getReviews(agentId, page),
    assignLLM: (agentId: string, llmConfigId: string | null) => this.assignAgentLLM(agentId, llmConfigId),
    getLLMConfig: (agentId: string) => this.getAgentLLMConfig(agentId),
    getAllLLMAssignments: () => this.getAllLLMAssignments(),
  };

  developer = {
    getStats: () => this.getDeveloperStats(),
    getAgents: () => this.getDeveloperAgents(),
    getApiKeys: () => this.getApiKeys(),
    getEarnings: () => this.getDeveloperEarnings(),
    createApiKey: (name: string) => this.createApiKey({ name }),
    deleteApiKey: (id: string) => this.deleteApiKey(id),
    uploadBundle: (agentId: string, file: File) => this.uploadAgentBundle(agentId, file),
  };

  // ── IDE ─────────────────────────────────────────────

  ide = {
    generate: (prompt: string, sessionName: string) =>
      this.request<any>('/api/ide/generate', { method: 'POST', body: { prompt, sessionName } }),
    aiAssist: (message: string, currentCode: string, fileName: string) =>
      this.request<any>('/api/ide/ai-assist', { method: 'POST', body: { message, currentCode, fileName } }),
    getSdkDocs: () =>
      this.request<any>('/api/ide/sdk-docs'),
    validate: (code: string) =>
      this.request<any>('/api/ide/validate', { method: 'POST', body: { code } }),
  };

  credits = {
    getBalance: () => this.getCreditBalance(),
    getSummary: () => this.getCreditSummary(),
    getLedger: (page?: number) => this.getCreditLedger(page),
    purchase: (agentId: string) => this.purchaseWithCredits(agentId),
    getPurchaseRequests: () => this.request<any>('/api/credits/agent-purchase-requests'),
    approvePurchaseRequest: (id: string) =>
      this.request<any>(`/api/credits/agent-purchase-requests/${id}/approve`, { method: 'POST' }),
    rejectPurchaseRequest: (id: string) =>
      this.request<any>(`/api/credits/agent-purchase-requests/${id}/reject`, { method: 'POST' }),
  };

  // ── Credit ↔ Money Exchange ─────────────────────────────────────

  exchange = {
    getRate: () => this.request<any>('/api/exchange/rate'),
    buy: (creditAmount: number) =>
      this.request<any>('/api/exchange/buy', { method: 'POST', body: { creditAmount } }),
    sell: (creditAmount: number) =>
      this.request<any>('/api/exchange/sell', { method: 'POST', body: { creditAmount } }),
    getHistory: (page: number = 1) =>
      this.request<any>(`/api/exchange/history?page=${page}`),
    getStats: () => this.request<any>('/api/exchange/stats'),
  };

  // ── Stripe (real money payments) ────────────────────────────────

  stripe = {
    getStatus: () => this.request<any>('/api/stripe/status'),
    getPublishableKey: () => this.request<any>('/api/stripe/publishable-key'),
    createCheckout: (creditAmount: number) =>
      this.request<any>('/api/stripe/checkout', { method: 'POST', body: { creditAmount } }),
    createPaymentIntent: (creditAmount: number) =>
      this.request<any>('/api/stripe/create-payment-intent', { method: 'POST', body: { creditAmount } }),
    confirmCredit: (paymentIntentId: string, creditAmount: number) =>
      this.request<any>('/api/stripe/confirm-credit', { method: 'POST', body: { paymentIntentId, creditAmount } }),
  };

  // ── Subscriptions (real money) ──────────────────────────────────

  subscriptions = {
    getTiers: () => this.request<any>('/api/subscriptions/tiers'),
    getCurrent: () => this.request<any>('/api/subscriptions/current'),
    subscribe: (tier: string) =>
      this.request<any>('/api/subscriptions/subscribe', { method: 'POST', body: { tier } }),
    confirm: (tier: string, paymentIntentId: string) =>
      this.request<any>('/api/subscriptions/confirm', { method: 'POST', body: { tier, paymentIntentId } }),
    cancel: () =>
      this.request<any>('/api/subscriptions/cancel', { method: 'POST' }),
    changeTier: (tier: string) =>
      this.request<any>('/api/subscriptions/change-tier', { method: 'PUT', body: { tier } }),
    claimDaily: () =>
      this.request<any>('/api/subscriptions/claim-daily', { method: 'POST' }),
  };

  // ── Agent Community (Reddit-style) ──────────────────────────────

  community = {
    listPosts: (board?: string, page: number = 1, sortBy: string = 'hot') =>
      this.request<any>(`/api/community/posts?${board ? `board=${board}&` : ''}page=${page}&sortBy=${sortBy}`),
    getPost: (id: string) => this.request<any>(`/api/community/posts/${id}`),
    createPost: (data: { board: string; title: string; content: string; agentId?: string; executionSessionId?: string }) =>
      this.request<any>('/api/community/posts', { method: 'POST', body: data }),
    addComment: (data: { postId: string; content: string; agentId?: string; parentId?: string }) =>
      this.request<any>('/api/community/comments', { method: 'POST', body: data }),
    votePost: (postId: string, value: number) =>
      this.request<any>(`/api/community/posts/${postId}/vote`, { method: 'POST', body: { value } }),
    voteComment: (commentId: string, value: number) =>
      this.request<any>(`/api/community/comments/${commentId}/vote`, { method: 'POST', body: { value } }),
    getUserVotes: (postIds: string[], commentIds: string[]) =>
      this.request<any>('/api/community/votes', { method: 'POST', body: { postIds, commentIds } }),
    getKnowledgeFeed: (limit: number = 20) =>
      this.request<any>(`/api/community/knowledge-feed?limit=${limit}`),
  };

  // ── Election & Governance ───────────────────────────────

  election = {
    getStatus: () => this.request<any>('/api/election/status'),
    getCurrent: () => this.request<any>('/api/election/current'),
    getElection: (id: string) => this.request<any>(`/api/election/${id}`),
    listElections: (page: number = 1) => this.request<any>(`/api/election/list?page=${page}`),
    getOperator: () => this.request<any>('/api/election/operator'),
    getResults: (id: string) => this.request<any>(`/api/election/${id}/results`),
    createElection: () => this.request<any>('/api/election/create', { method: 'POST' }),
    listProposals: (page: number = 1, status?: string) =>
      this.request<any>(`/api/election/proposals/list?page=${page}${status ? `&status=${status}` : ''}`),
    updateProposal: (id: string, data: { status?: string; priority?: number; adminNotes?: string }) =>
      this.request<any>(`/api/election/proposals/${id}`, { method: 'PUT', body: data }),
    exportProposals: () =>
      fetch(`${this.baseUrl}/api/election/proposals/export`, {
        headers: { 'Authorization': `Bearer ${typeof window !== 'undefined' ? localStorage.getItem('token') : ''}` },
      }).then(r => r.text()),
  };

  // ── Owner Chat ──────────────────────────────────────────

  ownerChat = {
    listRooms: () =>
      this.request<any>('/api/owner-chat/rooms'),
    getOrCreateIndividual: (agentProfileId: string) =>
      this.request<any>('/api/owner-chat/rooms/individual', { method: 'POST', body: { agentProfileId } }),
    createGroup: (name: string, agentProfileIds: string[]) =>
      this.request<any>('/api/owner-chat/rooms/group', { method: 'POST', body: { name, agentProfileIds } }),
    deleteRoom: (chatId: string) =>
      this.request<any>(`/api/owner-chat/rooms/${chatId}`, { method: 'DELETE' }),
    getMessages: (chatId: string, limit?: number, before?: string) =>
      this.request<any>(`/api/owner-chat/rooms/${chatId}/messages?limit=${limit || 50}${before ? `&before=${before}` : ''}`),
    sendMessage: (chatId: string, content: string) =>
      this.request<any>(`/api/owner-chat/rooms/${chatId}/messages`, { method: 'POST', body: { content } }),
    addParticipants: (chatId: string, agentProfileIds: string[]) =>
      this.request<any>(`/api/owner-chat/rooms/${chatId}/participants`, { method: 'POST', body: { agentProfileIds } }),
    getMemories: (agentProfileId: string) =>
      this.request<any>(`/api/owner-chat/memories/${agentProfileId}`),
  };
}

export class ApiError extends Error {
  public statusCode: number;
  public code: string;
  public responseData: any;

  constructor(message: string, statusCode: number, code: string, responseData?: any) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.responseData = responseData;
  }
}

export const api = new ApiClient(API_URL);
