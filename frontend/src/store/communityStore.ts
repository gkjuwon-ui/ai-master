/**
 * Community Store — State management for Reddit-style Agent Community
 * 
 * Replaces the P2P Swarm Store.
 * 
 * Manages:
 * - Post listing & filtering by board (KNOWHOW / CHAT)
 * - Post detail with comments
 * - Voting (upvote/downvote)
 * - Post & comment creation
 */

import { create } from 'zustand';
import { api } from '../lib/api';

interface CommunityAuthor {
  id: string;
  username: string;
  displayName: string;
  avatar?: string;
}

interface CommunityPost {
  id: string;
  authorId: string;
  author: CommunityAuthor;
  agentId?: string;
  agentName?: string;
  board: string;
  title: string;
  content: string;
  upvotes: number;
  downvotes: number;
  score: number;
  commentCount: number;
  comments?: CommunityComment[];
  executionSessionId?: string;
  executionOutcome?: string;
  createdAt: string;
  updatedAt: string;
}

interface CommunityComment {
  id: string;
  postId: string;
  authorId: string;
  author: CommunityAuthor;
  agentId?: string;
  agentName?: string;
  parentId?: string;
  content: string;
  upvotes: number;
  downvotes: number;
  score: number;
  createdAt: string;
  updatedAt: string;
}

interface CommunityState {
  // Post list
  posts: CommunityPost[];
  totalPosts: number;
  currentPage: number;
  totalPages: number;
  currentBoard: string | null;
  sortBy: 'hot' | 'top' | 'recent';

  // Single post view
  currentPost: CommunityPost | null;

  // User votes
  postVotes: Record<string, number>;
  commentVotes: Record<string, number>;

  // Loading states
  isLoading: boolean;
  isPostLoading: boolean;
  error: string | null;

  // Actions
  fetchPosts: (board?: string | null, page?: number, sortBy?: 'hot' | 'top' | 'recent') => Promise<void>;
  fetchPost: (postId: string) => Promise<void>;
  createPost: (data: { board: string; title: string; content: string; agentId?: string; executionSessionId?: string }) => Promise<void>;
  addComment: (data: { postId: string; content: string; agentId?: string; parentId?: string }) => Promise<void>;
  votePost: (postId: string, value: number) => Promise<void>;
  voteComment: (commentId: string, value: number) => Promise<void>;
  fetchUserVotes: (postIds: string[], commentIds: string[]) => Promise<void>;
  setBoard: (board: string | null) => void;
  setSortBy: (sortBy: 'hot' | 'top' | 'recent') => void;
}

export const useCommunityStore = create<CommunityState>((set, get) => ({
  posts: [],
  totalPosts: 0,
  currentPage: 1,
  totalPages: 1,
  currentBoard: null,
  sortBy: 'hot',
  currentPost: null,
  postVotes: {},
  commentVotes: {},
  isLoading: false,
  isPostLoading: false,
  error: null,

  fetchPosts: async (board, page = 1, sortBy) => {
    try {
      set({ isLoading: true, error: null });
      const effectiveBoard = board ?? get().currentBoard;
      const effectiveSortBy = sortBy ?? get().sortBy;
      const response = await api.community.listPosts(effectiveBoard || undefined, page, effectiveSortBy);
      const data = response?.data || response;
      set({
        posts: data.posts || [],
        totalPosts: data.total || 0,
        currentPage: data.page || 1,
        totalPages: data.totalPages || 1,
        currentBoard: effectiveBoard,
        isLoading: false,
      });
    } catch (error: any) {
      set({ error: error.message, isLoading: false });
    }
  },

  fetchPost: async (postId) => {
    try {
      set({ isPostLoading: true, error: null });
      const response = await api.community.getPost(postId);
      const data = response?.data || response;
      set({ currentPost: data, isPostLoading: false });

      // Fetch user votes for this post's comments
      if (data.comments?.length) {
        const commentIds = data.comments.map((c: CommunityComment) => c.id);
        get().fetchUserVotes([postId], commentIds);
      }
    } catch (error: any) {
      set({ error: error.message, isPostLoading: false });
    }
  },

  createPost: async (data) => {
    try {
      set({ error: null });
      await api.community.createPost(data);
      // Refresh the post list
      const { currentBoard, currentPage, sortBy } = get();
      await get().fetchPosts(currentBoard, currentPage, sortBy);
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },

  addComment: async (data) => {
    try {
      set({ error: null });
      await api.community.addComment(data);
      // Refresh the current post
      if (get().currentPost?.id === data.postId) {
        await get().fetchPost(data.postId);
      }
    } catch (error: any) {
      set({ error: error.message });
      throw error;
    }
  },

  votePost: async (postId, value) => {
    try {
      const response = await api.community.votePost(postId, value);
      const result = response?.data || response;

      // Update local vote state
      set(state => {
        const newPostVotes = { ...state.postVotes };
        if (result.action === 'removed') {
          delete newPostVotes[postId];
        } else {
          newPostVotes[postId] = result.value;
        }

        // Update post scores locally for instant feedback
        const updateScore = (post: CommunityPost) => {
          if (post.id !== postId) return post;
          const oldVote = state.postVotes[postId] || 0;
          const newVote = result.action === 'removed' ? 0 : result.value;
          const delta = newVote - oldVote;
          return {
            ...post,
            score: post.score + delta,
            upvotes: post.upvotes + (newVote === 1 ? 1 : 0) - (oldVote === 1 ? 1 : 0),
            downvotes: post.downvotes + (newVote === -1 ? 1 : 0) - (oldVote === -1 ? 1 : 0),
          };
        };

        return {
          postVotes: newPostVotes,
          posts: state.posts.map(updateScore),
          currentPost: state.currentPost ? updateScore(state.currentPost) : null,
        };
      });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  voteComment: async (commentId, value) => {
    try {
      const response = await api.community.voteComment(commentId, value);
      const result = response?.data || response;

      set(state => {
        const newCommentVotes = { ...state.commentVotes };
        if (result.action === 'removed') {
          delete newCommentVotes[commentId];
        } else {
          newCommentVotes[commentId] = result.value;
        }

        // Update comment scores in current post
        let updatedPost = state.currentPost;
        if (updatedPost?.comments) {
          updatedPost = {
            ...updatedPost,
            comments: updatedPost.comments.map(c => {
              if (c.id !== commentId) return c;
              const oldVote = state.commentVotes[commentId] || 0;
              const newVote = result.action === 'removed' ? 0 : result.value;
              const delta = newVote - oldVote;
              return {
                ...c,
                score: c.score + delta,
                upvotes: c.upvotes + (newVote === 1 ? 1 : 0) - (oldVote === 1 ? 1 : 0),
                downvotes: c.downvotes + (newVote === -1 ? 1 : 0) - (oldVote === -1 ? 1 : 0),
              };
            }),
          };
        }

        return {
          commentVotes: newCommentVotes,
          currentPost: updatedPost,
        };
      });
    } catch (error: any) {
      set({ error: error.message });
    }
  },

  fetchUserVotes: async (postIds, commentIds) => {
    try {
      const response = await api.community.getUserVotes(postIds, commentIds);
      const data = response?.data || response;
      set({
        postVotes: { ...get().postVotes, ...data.postVotes },
        commentVotes: { ...get().commentVotes, ...data.commentVotes },
      });
    } catch {
      // Non-critical
    }
  },

  setBoard: (board) => {
    set({ currentBoard: board });
    get().fetchPosts(board, 1);
  },

  setSortBy: (sortBy) => {
    set({ sortBy });
    get().fetchPosts(get().currentBoard, 1, sortBy);
  },
}));
