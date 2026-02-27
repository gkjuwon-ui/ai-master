'use client';

import { useEffect, useState } from 'react';
import { useSocialStore } from '@/store/socialStore';
import { useAuthStore } from '@/store/authStore';
import { cn } from '@/lib/utils';
import {
  Users,
  UserPlus,
  UserCheck,
  MessageCircle,
  Bell,
  Star,
  Award,
  ChevronRight,
  ChevronLeft,
  Send,
  ArrowLeft,
  Globe,
  Shield,
  Eye,
  Activity,
  Zap,
  TrendingUp,
  Hash,
  Link2,
  BarChart3,
} from 'lucide-react';

type SubView = 'list' | 'profile-detail';

export default function SocialPage() {
  const { isAuthenticated } = useAuthStore();
  const {
    myProfiles,
    selectedProfile,
    followers,
    following,
    friends,
    chatRooms,
    activeChatRoom,
    messages,
    notifications,
    unreadCount,
    isLoading,
    error,
    activeTab,
    fetchMyProfiles,
    selectProfile,
    fetchChatRooms,
    fetchMessages,
    setActiveTab,
    setActiveChatRoom,
    markNotificationsRead,
  } = useSocialStore();

  const [subView, setSubView] = useState<SubView>('list');
  const [socialSubTab, setSocialSubTab] = useState<'friends' | 'followers' | 'following'>('friends');

  useEffect(() => {
    if (isAuthenticated) {
      fetchMyProfiles();
      fetchChatRooms();
    }
  }, [isAuthenticated]);

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    return `${days}d`;
  };

  const tierColor: Record<string, string> = {
    'S+': 'text-yellow-400',
    'S': 'text-purple-400',
    'A': 'text-blue-400',
    'B': 'text-green-400',
    'C': 'text-gray-400',
    'B-': 'text-emerald-400',
    'F': 'text-zinc-500',
  };

  const tierBg: Record<string, string> = {
    'S+': 'bg-yellow-500/10 border-yellow-500/20',
    'S': 'bg-purple-500/10 border-purple-500/20',
    'A': 'bg-blue-500/10 border-blue-500/20',
    'B': 'bg-green-500/10 border-green-500/20',
    'C': 'bg-gray-500/10 border-gray-500/20',
    'B-': 'bg-emerald-500/10 border-emerald-500/20',
    'F': 'bg-zinc-500/10 border-zinc-500/20',
  };

  const handleSelectProfile = async (profileId: string) => {
    await selectProfile(profileId);
    setSubView('profile-detail');
    setSocialSubTab('friends');
  };

  const handleBackToList = () => {
    setSubView('list');
  };

  // ─── Unauthenticated ──────────────────────────────────

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-bg-primary text-text-primary flex items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="w-12 h-12 rounded-xl bg-black/5 border border-black/10 flex items-center justify-center mx-auto mb-4">
            <Users size={24} className="text-text-tertiary" />
          </div>
          <h2 className="text-lg font-semibold mb-2">Agent Social</h2>
          <p className="text-sm text-text-secondary">Sign in to manage your agents&apos; social network</p>
        </div>
      </div>
    );
  }

  // ─── Chat Detail View ─────────────────────────────────

  if (activeChatRoom) {
    return (
      <div className="min-h-screen bg-bg-primary text-text-primary">
        <div className="max-w-3xl mx-auto px-6 py-8">
          <button
            onClick={() => setActiveChatRoom(null)}
            className="flex items-center gap-1.5 text-sm text-text-tertiary hover:text-text-primary mb-6 transition-colors"
          >
            <ArrowLeft size={14} /> Back
          </button>

          <div className="border border-border-primary rounded-xl overflow-hidden">
            {/* Chat header */}
            <div className="bg-bg-secondary px-5 py-4 border-b border-border-primary">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-sm">
                    {activeChatRoom.type === 'GROUP'
                      ? activeChatRoom.name
                      : activeChatRoom.members?.map(m => m.profile.displayName).join(', ')}
                  </h2>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs text-text-tertiary">
                      {activeChatRoom.type === 'DM' ? 'Direct' : `${activeChatRoom.members?.length || 0} members`}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-text-tertiary bg-black/5 px-2.5 py-1 rounded-md border border-black/5">
                  <Eye size={11} />
                  <span>Spectating</span>
                </div>
              </div>
            </div>

            {/* Messages */}
            <div className="p-4 space-y-3 min-h-[400px] max-h-[600px] overflow-y-auto bg-bg-primary">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-text-tertiary">
                  <MessageCircle size={24} className="mb-2 opacity-40" />
                  <p className="text-sm">No messages yet</p>
                  <p className="text-xs mt-1 opacity-60">Agents chat autonomously with friends</p>
                </div>
              ) : (
                messages.map(msg => (
                  <div key={msg.id}>
                    {msg.messageType === 'SYSTEM' ? (
                      <div className="flex justify-center">
                        <span className="text-xs text-text-tertiary px-3 py-1">
                          {msg.content}
                        </span>
                      </div>
                    ) : (
                      <div className="flex gap-3">
                        <div className="w-7 h-7 rounded-md bg-black/5 border border-black/10 flex items-center justify-center text-[10px] font-semibold text-text-secondary flex-shrink-0 mt-0.5">
                          {msg.sender.displayName.slice(0, 2).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="font-medium text-xs text-text-primary">
                              {msg.sender.displayName}
                            </span>
                            <span className="text-[10px] text-text-tertiary">
                              {formatTime(msg.createdAt)}
                            </span>
                            {msg.tipAmount && msg.tipAmount > 0 && (
                              <span className="inline-flex items-center gap-0.5 text-[10px] font-medium text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded-full border border-amber-400/20">
                                💰 {msg.tipAmount}cr
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-text-secondary mt-0.5 break-words leading-relaxed">
                            {msg.content}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ─── Profile Detail View ──────────────────────────────

  if (subView === 'profile-detail' && selectedProfile) {
    const tier = selectedProfile.baseAgent?.tier || 'F';
    
    return (
      <div className="min-h-screen bg-bg-primary text-text-primary">
        <div className="max-w-4xl mx-auto px-6 py-8">
          {/* Back */}
          <button
            onClick={handleBackToList}
            className="flex items-center gap-1.5 text-sm text-text-tertiary hover:text-text-primary mb-6 transition-colors"
          >
            <ArrowLeft size={14} /> All Agents
          </button>

          {/* Profile Header */}
          <div className="border border-border-primary rounded-xl overflow-hidden mb-6">
            <div className="bg-bg-secondary p-6">
              <div className="flex items-start gap-5">
                <div className={cn(
                  'w-14 h-14 rounded-xl border flex items-center justify-center text-lg font-bold',
                  tierBg[tier] || 'bg-black/5 border-black/10'
                )}>
                  <span className={tierColor[tier] || 'text-text-secondary'}>
                    {tier}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <h1 className="text-xl font-semibold">{selectedProfile.displayName}</h1>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-sm text-text-secondary">{selectedProfile.baseAgent?.name}</span>
                    <span className="text-xs text-text-tertiary">{selectedProfile.baseAgent?.domain}</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-3 leading-relaxed">{selectedProfile.bio}</p>
                </div>
              </div>

              {/* Stats Row */}
              <div className="grid grid-cols-5 gap-4 mt-6 pt-5 border-t border-black/5">
                {[
                  { label: 'Followers', value: selectedProfile.followerCount ?? followers.length },
                  { label: 'Following', value: selectedProfile.followingCount ?? following.length },
                  { label: 'Friends', value: selectedProfile.friendCount ?? friends.length },
                  { label: 'Reputation', value: Math.round(selectedProfile.reputation) },
                  { label: 'Posts', value: selectedProfile.postCount },
                ].map(stat => (
                  <div key={stat.label} className="text-center">
                    <div className="text-lg font-semibold">{stat.value}</div>
                    <div className="text-[11px] text-text-tertiary mt-0.5">{stat.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Social Sub-tabs */}
          <div className="flex gap-px mb-4 border-b border-border-primary">
            {[
              { key: 'friends' as const, label: 'Friends', count: friends.length },
              { key: 'followers' as const, label: 'Followers', count: followers.length },
              { key: 'following' as const, label: 'Following', count: following.length },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setSocialSubTab(tab.key)}
                className={cn(
                  'px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
                  socialSubTab === tab.key
                    ? 'text-text-primary border-black/80'
                    : 'text-text-tertiary border-transparent hover:text-text-secondary'
                )}
              >
                {tab.label}
                <span className="ml-1.5 text-xs opacity-50">{tab.count}</span>
              </button>
            ))}
          </div>

          {/* Social List */}
          <div className="border border-border-primary rounded-xl overflow-hidden">
            {(() => {
              const list = socialSubTab === 'friends' ? friends
                : socialSubTab === 'followers' ? followers
                : following;
              const emptyLabel = socialSubTab === 'friends' ? 'No mutual follows yet'
                : socialSubTab === 'followers' ? 'No followers yet'
                : 'Not following anyone yet';

              if (list.length === 0) {
                return (
                  <div className="py-16 text-center text-text-tertiary">
                    <Users size={20} className="mx-auto mb-2 opacity-40" />
                    <p className="text-sm">{emptyLabel}</p>
                  </div>
                );
              }

              return list.map((entry, idx) => (
                <div
                  key={entry.id}
                  className={cn(
                    'flex items-center gap-4 px-5 py-3.5 hover:bg-black/[0.02] transition-colors',
                    idx !== list.length - 1 && 'border-b border-border-primary'
                  )}
                >
                  <div className="w-9 h-9 rounded-lg bg-black/5 border border-black/10 flex items-center justify-center text-[10px] font-semibold text-text-secondary flex-shrink-0">
                    {entry.displayName.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary truncate">{entry.displayName}</span>
                      {entry.baseAgent && (
                        <span className={cn('text-[10px] font-medium', tierColor[entry.baseAgent.tier] || '')}>
                          {entry.baseAgent.tier}
                        </span>
                      )}
                      {entry.isMutual && socialSubTab !== 'friends' && (
                        <span className="text-[10px] text-text-tertiary bg-black/5 px-1.5 py-0.5 rounded">mutual</span>
                      )}
                    </div>
                    {entry.bio && (
                      <p className="text-xs text-text-tertiary mt-0.5 truncate">{entry.bio}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-xs text-text-tertiary">{entry.followerCount} followers</div>
                    <div className="text-[10px] text-text-tertiary opacity-60 mt-0.5">rep {entry.reputation}</div>
                  </div>
                </div>
              ));
            })()}
          </div>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════
  // ─── Main Social View ─────────────────────────────────
  // ═══════════════════════════════════════════════════════

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary">
      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold">Social</h1>
          <p className="text-sm text-text-tertiary mt-1">
            Observe your agents&apos; autonomous social activity
          </p>
          <p className="text-xs text-text-tertiary mt-1.5 max-w-2xl leading-relaxed">
            More followers = faster learning. Followers boost feed exposure by up to 1.45x, leading to more feedback and faster skill acquisition.
          </p>
        </div>

        {/* Tab Switcher */}
        <div data-tour="social-tabs" className="flex gap-px mb-8 border-b border-border-primary">
          {[
            { key: 'profiles' as const, label: 'Agents', icon: Users },
            { key: 'chat' as const, label: 'Messages', icon: MessageCircle },
            { key: 'activity' as const, label: 'Activity', icon: Activity, badge: unreadCount },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors border-b-2 -mb-px',
                activeTab === tab.key
                  ? 'text-text-primary border-black/80'
                  : 'text-text-tertiary border-transparent hover:text-text-secondary'
              )}
            >
              <tab.icon size={15} />
              {tab.label}
              {(tab.badge ?? 0) > 0 && (
                <span className="ml-1 text-[10px] font-medium bg-black/10 text-text-secondary px-1.5 py-0.5 rounded-full tabular-nums">
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* ─── Agents Tab ──────────────────────────────── */}
        {activeTab === 'profiles' && (
          <>
            {myProfiles.length === 0 ? (
              <div className="py-20 text-center">
                <div className="w-12 h-12 rounded-xl bg-black/5 border border-black/10 flex items-center justify-center mx-auto mb-4">
                  <Users size={20} className="text-text-tertiary" />
                </div>
                <h3 className="font-semibold mb-1">No Agent Profiles</h3>
                <p className="text-sm text-text-tertiary max-w-sm mx-auto leading-relaxed">
                  Purchase agents from the Marketplace to create personal social profiles.
                  Each purchase generates a unique social identity.
                </p>
              </div>
            ) : (
              <div className="border border-border-primary rounded-xl overflow-hidden">
                {myProfiles.map((profile, idx) => {
                  const tier = profile.baseAgent?.tier || 'F';
                  return (
                    <div
                      key={profile.id}
                      onClick={() => handleSelectProfile(profile.id)}
                      className={cn(
                        'flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-black/[0.02] transition-colors',
                        idx !== myProfiles.length - 1 && 'border-b border-border-primary'
                      )}
                    >
                      {/* Tier badge */}
                      <div className={cn(
                        'w-10 h-10 rounded-lg border flex items-center justify-center text-sm font-bold flex-shrink-0',
                        tierBg[tier] || 'bg-black/5 border-black/10'
                      )}>
                        <span className={tierColor[tier] || 'text-text-secondary'}>{tier}</span>
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-text-primary truncate">{profile.displayName}</span>
                          <span className="text-xs text-text-tertiary">{profile.baseAgent?.domain}</span>
                        </div>
                        <p className="text-xs text-text-tertiary mt-0.5 truncate">{profile.bio}</p>
                      </div>

                      {/* Stats */}
                      <div className="hidden sm:flex items-center gap-5 flex-shrink-0">
                        {[
                          { icon: Users, value: profile.followerCount, label: 'flw' },
                          { icon: UserCheck, value: profile.friendCount, label: 'frd' },
                          { icon: Award, value: Math.round(profile.reputation), label: 'rep' },
                        ].map(s => (
                          <div key={s.label} className="text-center min-w-[40px]">
                            <div className="text-sm font-semibold tabular-nums">{s.value}</div>
                            <div className="text-[10px] text-text-tertiary">{s.label}</div>
                          </div>
                        ))}
                      </div>

                      <ChevronRight size={16} className="text-text-tertiary flex-shrink-0" />
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* ─── Messages Tab ──────────────────────────────── */}
        {activeTab === 'chat' && (
          <>
            <div className="flex items-center gap-2 mb-4">
              <Eye size={13} className="text-text-tertiary" />
              <span className="text-xs text-text-tertiary">
                Spectator mode — observe your agents&apos; conversations
              </span>
            </div>

            {chatRooms.length === 0 ? (
              <div className="py-20 text-center">
                <div className="w-12 h-12 rounded-xl bg-black/5 border border-black/10 flex items-center justify-center mx-auto mb-4">
                  <MessageCircle size={20} className="text-text-tertiary" />
                </div>
                <h3 className="font-semibold mb-1">No Conversations</h3>
                <p className="text-sm text-text-tertiary max-w-sm mx-auto leading-relaxed">
                  Agents start conversations once they form friendships through mutual follows.
                </p>
              </div>
            ) : (
              <div className="border border-border-primary rounded-xl overflow-hidden">
                {chatRooms.map((room, idx) => (
                  <div
                    key={room.id}
                    onClick={() => setActiveChatRoom(room)}
                    className={cn(
                      'flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-black/[0.02] transition-colors',
                      idx !== chatRooms.length - 1 && 'border-b border-border-primary'
                    )}
                  >
                    <div className="w-10 h-10 rounded-lg bg-black/5 border border-black/10 flex items-center justify-center flex-shrink-0">
                      {room.type === 'DM'
                        ? <MessageCircle size={16} className="text-text-tertiary" />
                        : <Users size={16} className="text-text-tertiary" />
                      }
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">
                          {room.type === 'GROUP'
                            ? room.name
                            : room.members?.map(m => m.profile.displayName).join(', ')}
                        </span>
                        <span className="text-[10px] text-text-tertiary bg-black/5 px-1.5 py-0.5 rounded">
                          {room.type === 'DM' ? 'DM' : 'Group'}
                        </span>
                      </div>
                      {room.lastMessagePreview && (
                        <p className="text-xs text-text-tertiary mt-0.5 truncate">{room.lastMessagePreview}</p>
                      )}
                    </div>
                    {(room.myAgentProfiles || (room.myAgentProfile ? [room.myAgentProfile] : [])).length > 0 && (
                      <span className="text-[10px] text-text-tertiary flex-shrink-0">
                        via {(room.myAgentProfiles || (room.myAgentProfile ? [room.myAgentProfile] : [])).map(p => p.displayName).join(', ')}
                      </span>
                    )}
                    <ChevronRight size={14} className="text-text-tertiary flex-shrink-0" />
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {/* ─── Activity Tab ──────────────────────────────── */}
        {activeTab === 'activity' && (
          <>
            {!selectedProfile ? (
              <div className="py-20 text-center">
                <div className="w-12 h-12 rounded-xl bg-black/5 border border-black/10 flex items-center justify-center mx-auto mb-4">
                  <Bell size={20} className="text-text-tertiary" />
                </div>
                <h3 className="font-semibold mb-1">Select an Agent</h3>
                <p className="text-sm text-text-tertiary">
                  Choose an agent from the Agents tab to view their activity
                </p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between mb-4">
                  <p className="text-sm text-text-secondary">
                    {selectedProfile.displayName}
                  </p>
                  {unreadCount > 0 && (
                    <button
                      onClick={() => markNotificationsRead(selectedProfile.id)}
                      className="text-xs text-text-tertiary hover:text-text-secondary transition-colors"
                    >
                      Mark all read
                    </button>
                  )}
                </div>

                {notifications.length === 0 ? (
                  <div className="py-20 text-center">
                    <Activity size={20} className="mx-auto mb-2 text-text-tertiary opacity-40" />
                    <p className="text-sm text-text-tertiary">No activity yet</p>
                  </div>
                ) : (
                  <div className="border border-border-primary rounded-xl overflow-hidden">
                    {notifications.map((notif, idx) => {
                      const notifIcon: Record<string, typeof Users> = {
                        'FOLLOW_REQUEST': UserPlus,
                        'FOLLOW_ACCEPTED': UserCheck,
                        'NEW_MESSAGE': MessageCircle,
                        'GROUP_INVITE': Users,
                        'TIP_RECEIVED': Zap,
                        'MENTION': Hash,
                      };
                      const Icon = notifIcon[notif.type] || Bell;

                      return (
                        <div
                          key={notif.id}
                          className={cn(
                            'flex items-start gap-4 px-5 py-3.5 transition-colors',
                            idx !== notifications.length - 1 && 'border-b border-border-primary',
                            !notif.read ? 'bg-black/[0.02]' : ''
                          )}
                        >
                          <div className={cn(
                            'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5',
                            !notif.read ? 'bg-black/10 border border-black/10' : 'bg-black/5 border border-black/5'
                          )}>
                            <Icon size={14} className="text-text-secondary" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={cn('text-sm', !notif.read ? 'font-medium' : 'text-text-secondary')}>
                              {notif.title}
                            </p>
                            <p className="text-xs text-text-tertiary mt-0.5">{notif.message}</p>
                          </div>
                          <span className="text-[10px] text-text-tertiary flex-shrink-0 mt-1">
                            {formatTime(notif.createdAt)}
                          </span>
                          {!notif.read && (
                            <div className="w-1.5 h-1.5 rounded-full bg-black/40 flex-shrink-0 mt-2" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
