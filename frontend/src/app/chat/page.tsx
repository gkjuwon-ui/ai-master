'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useOwnerChatStore, OwnerChatRoom, OwnerChatMessage } from '@/store/ownerChatStore';
import { useSocialStore } from '@/store/socialStore';
import { useAuthStore } from '@/store/authStore';
import { cn } from '@/lib/utils';
import {
  MessageCircle,
  Users,
  Plus,
  Send,
  Trash2,
  UserPlus,
  ArrowLeft,
  Bot,
  Sparkles,
  Brain,
  X,
  Check,
} from 'lucide-react';

export default function ChatPage() {
  const { isAuthenticated } = useAuthStore();
  const {
    rooms,
    activeRoom,
    messages,
    isLoading,
    isSending,
    error,
    loadRooms,
    openIndividualChat,
    createGroupChat,
    selectRoom,
    sendMessage,
    deleteRoom,
    clearError,
    subscribeGroupDiscussion,
  } = useOwnerChatStore();
  const { myProfiles, fetchMyProfiles } = useSocialStore();

  const [input, setInput] = useState('');
  const [showNewGroup, setShowNewGroup] = useState(false);
  const [groupName, setGroupName] = useState('');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [mobileView, setMobileView] = useState<'list' | 'chat'>('list');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isAuthenticated) {
      loadRooms();
      fetchMyProfiles();
    }
  }, [isAuthenticated]);

  // Subscribe to WebSocket for group discussion messages (agents reacting to each other)
  useEffect(() => {
    if (isAuthenticated) {
      const unsub = subscribeGroupDiscussion();
      return unsub;
    }
  }, [isAuthenticated, subscribeGroupDiscussion]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isSending) return;
    const msg = input.trim();
    setInput('');
    await sendMessage(msg);
  }, [input, isSending, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCreateGroup = async () => {
    if (!groupName.trim() || selectedAgents.length < 2) return;
    await createGroupChat(groupName.trim(), selectedAgents);
    setShowNewGroup(false);
    setGroupName('');
    setSelectedAgents([]);
    setMobileView('chat');
  };

  const handleSelectRoom = async (room: OwnerChatRoom) => {
    await selectRoom(room.id);
    setMobileView('chat');
  };

  const handleStartChat = async (profileId: string) => {
    await openIndividualChat(profileId);
    setMobileView('chat');
  };

  const getAgentAvatar = (room: OwnerChatRoom) => {
    if (room.type === 'INDIVIDUAL' && room.agentProfile) {
      return room.agentProfile.avatar || room.agentProfile.baseAgent?.icon;
    }
    return null;
  };

  const getRoomName = (room: OwnerChatRoom) => {
    if (room.type === 'GROUP') return room.name || 'Group Chat';
    if (room.agentProfile) return room.agentProfile.displayName;
    return 'Chat';
  };

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d`;
    return date.toLocaleDateString();
  };

  if (!isAuthenticated) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-text-secondary">Please log in to access chat.</p>
      </div>
    );
  }

  // ─── Agent List (no active chats yet) ──────────────
  const agentsWithoutChat = myProfiles.filter(
    p => !rooms.some(r => r.type === 'INDIVIDUAL' && r.agentProfileId === p.id)
  );

  return (
    <div className="flex h-full overflow-hidden">
      {/* ═══════════════════════════════════════════════════════ */}
      {/* Left Sidebar — Chat Rooms + Agent List                  */}
      {/* ═══════════════════════════════════════════════════════ */}
      <div className={cn(
        'w-80 border-r border-border-primary bg-bg-secondary flex flex-col',
        mobileView === 'chat' && 'hidden md:flex',
        mobileView === 'list' && 'flex-1 md:flex-none md:w-80'
      )}>
        {/* Header */}
        <div className="h-14 px-4 flex items-center justify-between border-b border-border-primary">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <MessageCircle size={20} />
            Chat
          </h2>
          <button
            onClick={() => setShowNewGroup(true)}
            className="p-2 rounded-lg hover:bg-bg-elevated text-text-secondary hover:text-text-primary transition-colors"
            title="Create Group Chat"
          >
            <Plus size={18} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Existing Chat Rooms */}
          {rooms.length > 0 && (
            <div className="py-2">
              <div className="px-4 py-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wider">
                Conversations
              </div>
              {rooms.map(room => (
                <button
                  key={room.id}
                  onClick={() => handleSelectRoom(room)}
                  className={cn(
                    'w-full px-4 py-3 flex items-center gap-3 hover:bg-bg-elevated transition-colors text-left',
                    activeRoom?.id === room.id && 'bg-bg-elevated border-r-2 border-accent-primary'
                  )}
                >
                  {/* Avatar */}
                  <div className="w-10 h-10 rounded-full bg-bg-tertiary flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {room.type === 'GROUP' ? (
                      <Users size={18} className="text-text-tertiary" />
                    ) : getAgentAvatar(room) ? (
                      <img src={getAgentAvatar(room)!} className="w-full h-full object-cover" alt="" />
                    ) : (
                      <Bot size={18} className="text-text-tertiary" />
                    )}
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary truncate">
                        {getRoomName(room)}
                      </span>
                      {room.lastMessageAt && (
                        <span className="text-xs text-text-tertiary flex-shrink-0 ml-2">
                          {formatTime(room.lastMessageAt)}
                        </span>
                      )}
                    </div>
                    {room.lastMessagePreview && (
                      <p className="text-xs text-text-tertiary truncate mt-0.5">
                        {room.lastMessagePreview}
                      </p>
                    )}
                    {room.type === 'GROUP' && room.participants.length > 0 && (
                      <p className="text-xs text-text-tertiary mt-0.5">
                        {room.participants.length} agents
                      </p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Agents to Start Chat With */}
          {agentsWithoutChat.length > 0 && (
            <div className="py-2">
              <div className="px-4 py-1.5 text-xs font-medium text-text-tertiary uppercase tracking-wider">
                Start New Chat
              </div>
              {agentsWithoutChat.map(profile => (
                <button
                  key={profile.id}
                  onClick={() => handleStartChat(profile.id)}
                  className="w-full px-4 py-3 flex items-center gap-3 hover:bg-bg-elevated transition-colors text-left"
                >
                  <div className="w-10 h-10 rounded-full bg-bg-tertiary flex items-center justify-center flex-shrink-0 overflow-hidden">
                    {profile.avatar || (profile as any).baseAgent?.icon ? (
                      <img src={profile.avatar || (profile as any).baseAgent?.icon} className="w-full h-full object-cover" alt="" />
                    ) : (
                      <Bot size={18} className="text-text-tertiary" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-text-secondary truncate block">{profile.displayName}</span>
                    <span className="text-xs text-text-tertiary">Tap to start chatting</span>
                  </div>
                  <MessageCircle size={16} className="text-text-tertiary" />
                </button>
              ))}
            </div>
          )}

          {rooms.length === 0 && agentsWithoutChat.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
              <Bot size={48} className="text-text-tertiary mb-4" />
              <p className="text-text-secondary text-sm">No agents yet</p>
              <p className="text-text-tertiary text-xs mt-1">Purchase agents from the Marketplace to start chatting</p>
            </div>
          )}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════ */}
      {/* Main Chat Area                                          */}
      {/* ═══════════════════════════════════════════════════════ */}
      <div className={cn(
        'flex-1 flex flex-col',
        mobileView === 'list' && 'hidden md:flex'
      )}>
        {activeRoom ? (
          <>
            {/* Chat Header */}
            <div className="h-14 px-4 flex items-center gap-3 border-b border-border-primary bg-bg-secondary">
              <button
                onClick={() => setMobileView('list')}
                className="md:hidden p-1.5 rounded-lg hover:bg-bg-elevated text-text-secondary"
              >
                <ArrowLeft size={18} />
              </button>
              <div className="w-8 h-8 rounded-full bg-bg-tertiary flex items-center justify-center overflow-hidden">
                {activeRoom.type === 'GROUP' ? (
                  <Users size={16} className="text-text-tertiary" />
                ) : getAgentAvatar(activeRoom) ? (
                  <img src={getAgentAvatar(activeRoom)!} className="w-full h-full object-cover" alt="" />
                ) : (
                  <Bot size={16} className="text-text-tertiary" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium text-text-primary truncate">
                  {getRoomName(activeRoom)}
                </h3>
                {activeRoom.type === 'GROUP' && (
                  <p className="text-xs text-text-tertiary">
                    {activeRoom.participants.map(p => p.agentProfile.displayName).join(', ')}
                  </p>
                )}
              </div>
              <button
                onClick={() => {
                  if (confirm('Delete this conversation?')) {
                    deleteRoom(activeRoom.id);
                    setMobileView('list');
                  }
                }}
                className="p-2 rounded-lg hover:bg-red-500/10 text-text-tertiary hover:text-red-400 transition-colors"
                title="Delete conversation"
              >
                <Trash2 size={16} />
              </button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.length === 0 && !isLoading && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <Sparkles size={40} className="text-accent-primary/60 mb-3" />
                  <p className="text-text-secondary text-sm font-medium">Start a conversation</p>
                  <p className="text-text-tertiary text-xs mt-1 max-w-sm">
                    Chat with your agent like you're talking to a friend. They remember your executions and learn from conversations.
                  </p>
                </div>
              )}

              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} chatType={activeRoom.type} />
              ))}

              {isSending && (
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-bg-tertiary flex items-center justify-center">
                    <Bot size={14} className="text-text-tertiary" />
                  </div>
                  <div className="bg-bg-elevated border border-border-primary rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                      <div className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                      <div className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="px-4 pb-4 pt-2">
              <div className="flex items-end gap-2 bg-bg-elevated border border-border-primary rounded-xl px-4 py-2.5 focus-within:border-accent-primary/50 transition-colors">
                <textarea
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type a message..."
                  rows={1}
                  className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary resize-none outline-none max-h-32"
                  style={{ minHeight: '24px' }}
                  disabled={isSending}
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || isSending}
                  className={cn(
                    'p-2 rounded-lg transition-all flex-shrink-0',
                    input.trim() && !isSending
                      ? 'bg-accent-primary text-white hover:bg-accent-primary/90'
                      : 'text-text-tertiary'
                  )}
                >
                  <Send size={16} />
                </button>
              </div>
            </div>
          </>
        ) : (
          /* No Room Selected */
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
            <div className="w-20 h-20 rounded-full bg-bg-elevated flex items-center justify-center mb-4">
              <MessageCircle size={32} className="text-text-tertiary" />
            </div>
            <h3 className="text-lg font-medium text-text-primary">Agent Chat</h3>
            <p className="text-sm text-text-tertiary mt-2 max-w-sm">
              Chat directly with your agents. They remember your past executions, 
              learn about you over time, and develop unique personalities.
            </p>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════════════════════ */}
      {/* New Group Chat Modal                                    */}
      {/* ═══════════════════════════════════════════════════════ */}
      {showNewGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-bg-primary border border-border-primary rounded-xl w-full max-w-md mx-4 max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="px-5 py-4 border-b border-border-primary flex items-center justify-between">
              <h3 className="text-base font-semibold text-text-primary">Create Group Chat</h3>
              <button
                onClick={() => { setShowNewGroup(false); setSelectedAgents([]); setGroupName(''); }}
                className="p-1.5 rounded-lg hover:bg-bg-elevated text-text-tertiary"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {/* Group Name */}
              <div>
                <label className="text-xs font-medium text-text-secondary block mb-1.5">Group Name</label>
                <input
                  type="text"
                  value={groupName}
                  onChange={e => setGroupName(e.target.value)}
                  placeholder="e.g. Research Team"
                  className="w-full bg-bg-elevated border border-border-primary rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary outline-none focus:border-accent-primary/50"
                />
              </div>

              {/* Select Agents */}
              <div>
                <label className="text-xs font-medium text-text-secondary block mb-1.5">
                  Select Agents ({selectedAgents.length} selected, min 2)
                </label>
                <div className="space-y-1">
                  {myProfiles.map(profile => {
                    const isSelected = selectedAgents.includes(profile.id);
                    return (
                      <button
                        key={profile.id}
                        onClick={() => {
                          setSelectedAgents(prev =>
                            isSelected ? prev.filter(id => id !== profile.id) : [...prev, profile.id]
                          );
                        }}
                        className={cn(
                          'w-full px-3 py-2.5 flex items-center gap-3 rounded-lg transition-colors text-left',
                          isSelected ? 'bg-accent-primary/10 border border-accent-primary/30' : 'hover:bg-bg-elevated border border-transparent'
                        )}
                      >
                        <div className="w-8 h-8 rounded-full bg-bg-tertiary flex items-center justify-center overflow-hidden">
                          {profile.avatar || (profile as any).baseAgent?.icon ? (
                            <img src={profile.avatar || (profile as any).baseAgent?.icon} className="w-full h-full object-cover" alt="" />
                          ) : (
                            <Bot size={14} className="text-text-tertiary" />
                          )}
                        </div>
                        <span className="flex-1 text-sm text-text-primary truncate">{profile.displayName}</span>
                        {isSelected && <Check size={16} className="text-accent-primary" />}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-4 border-t border-border-primary flex justify-end gap-2">
              <button
                onClick={() => { setShowNewGroup(false); setSelectedAgents([]); setGroupName(''); }}
                className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateGroup}
                disabled={!groupName.trim() || selectedAgents.length < 2}
                className={cn(
                  'px-4 py-2 text-sm rounded-lg font-medium transition-colors',
                  groupName.trim() && selectedAgents.length >= 2
                    ? 'bg-accent-primary text-white hover:bg-accent-primary/90'
                    : 'bg-bg-elevated text-text-tertiary cursor-not-allowed'
                )}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Toast */}
      {error && (
        <div className="fixed bottom-4 right-4 z-50 bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-lg max-w-sm">
          <div className="flex items-center justify-between gap-2">
            <span>{error}</span>
            <button onClick={clearError} className="text-red-400 hover:text-red-300">
              <X size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Message Bubble Component
// ═══════════════════════════════════════════════════════════════

function MessageBubble({ message, chatType }: { message: OwnerChatMessage; chatType: string }) {
  const isUser = message.role === 'USER';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%]">
          <div className="bg-accent-primary text-white rounded-2xl rounded-tr-sm px-4 py-2.5">
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          </div>
          <div className="text-xs text-text-tertiary mt-1 text-right">
            {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-3">
      {/* Agent Avatar */}
      <div className="w-8 h-8 rounded-full bg-bg-tertiary flex items-center justify-center flex-shrink-0 overflow-hidden">
        {message.agentProfile?.avatar ? (
          <img src={message.agentProfile.avatar} className="w-full h-full object-cover" alt="" />
        ) : (
          <Bot size={14} className="text-text-tertiary" />
        )}
      </div>

      <div className="max-w-[75%]">
        {/* Agent name (in group chats or proactive messages) */}
        {(chatType === 'GROUP' || message.isProactive) && message.agentProfile && (
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-text-secondary">
              {message.agentProfile.displayName}
            </span>
            {message.isProactive && (
              <span className="text-xs text-accent-primary/70 flex items-center gap-1">
                <Sparkles size={10} />
                reached out
              </span>
            )}
          </div>
        )}

        {/* Proactive reason */}
        {message.isProactive && message.proactiveReason && (
          <div className="text-xs text-text-tertiary italic mb-1 flex items-center gap-1">
            <Brain size={10} />
            {message.proactiveReason}
          </div>
        )}

        <div className="bg-bg-elevated border border-border-primary rounded-2xl rounded-tl-sm px-4 py-2.5">
          <p className="text-sm text-text-primary whitespace-pre-wrap">{message.content}</p>
        </div>
        <div className="text-xs text-text-tertiary mt-1">
          {new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}
