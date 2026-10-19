'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { api, Conversation, ChatMessage, Memory } from '@/lib/api';
import { MarkdownContent } from '@/components/MarkdownContent';
import {
  MessageSquare,
  Plus,
  Trash2,
  Pin,
  Sparkles,
  Brain,
  ChevronRight,
  ChevronLeft,
  Bot,
  User as UserIcon,
  RotateCcw,
  AlertCircle,
  Edit2,
  Check,
  X,
  Database,
  Search,
  ArrowUp,
} from 'lucide-react';

export default function ChatPage() {
  const router = useRouter();
  const { profile, loading: authLoading } = useAuth();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [threadsOpen, setThreadsOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Inline conversation renaming
  const [editingConvId, setEditingConvId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  // Expandable recalled memory details
  const [expandedMemoryMsgId, setExpandedMemoryMsgId] = useState<string | null>(null);
  const [memoryDetailsCache, setMemoryDetailsCache] = useState<Record<string, Memory>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!authLoading && !profile) {
      router.push('/login');
    }
  }, [profile, authLoading, router]);

  useEffect(() => {
    if (profile) {
      loadConversations();
    }
  }, [profile]);

  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText, isLoading]);

  // Auto-resize textarea as user types
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 160)}px`;
    }
  }, [inputPrompt]);

  const loadConversations = async () => {
    try {
      const data = await api.listConversations();
      setConversations(data);
      if (data.length > 0 && !activeConvId) {
        setActiveConvId(data[0].id);
      }
    } catch (err: any) {
      console.error('Failed to load conversations:', err);
    }
  };

  const loadMessages = async (convId: string) => {
    try {
      setErrorMsg(null);
      const msgs = await api.getMessages(convId);
      setMessages(msgs);
    } catch (err: any) {
      console.error('Failed to load messages:', err);
      setErrorMsg('Failed to load conversation history.');
    }
  };

  const handleNewChat = async () => {
    try {
      const newConv = await api.createConversation('New Conversation');
      setConversations([newConv, ...conversations]);
      setActiveConvId(newConv.id);
      setMessages([]);
      setInputPrompt('');
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
        inputRef.current.focus();
      }
    } catch (err: any) {
      console.error('Failed to create new conversation:', err);
    }
  };

  const handleDeleteConversation = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Permanently delete this conversation thread?')) return;
    try {
      await api.deleteConversation(id);
      const updated = conversations.filter((c) => c.id !== id);
      setConversations(updated);
      if (activeConvId === id) {
        setActiveConvId(updated.length > 0 ? updated[0].id : null);
      }
    } catch (err: any) {
      console.error('Failed to delete conversation:', err);
    }
  };

  const handleStartRename = (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    setEditingConvId(conv.id);
    setEditingTitle(conv.title);
  };

  const handleSaveRename = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!editingTitle.trim()) return;
    try {
      const updated = await api.updateConversation(id, { title: editingTitle.trim() });
      setConversations(conversations.map((c) => (c.id === id ? updated : c)));
      setEditingConvId(null);
    } catch (err) {
      console.error('Failed to rename conversation:', err);
    }
  };

  const handleTogglePin = async (e: React.MouseEvent, conv: Conversation) => {
    e.stopPropagation();
    try {
      const updated = await api.updateConversation(conv.id, { is_pinned: !conv.is_pinned });
      setConversations(
        conversations
          .map((c) => (c.id === conv.id ? updated : c))
          .sort((a, b) => (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0))
      );
    } catch (err) {
      console.error('Failed to pin conversation:', err);
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const prompt = (textToSend || inputPrompt).trim();
    if (!prompt || isLoading) return;

    let targetConvId = activeConvId;
    if (!targetConvId) {
      try {
        const newConv = await api.createConversation(prompt.slice(0, 32) + '...');
        setConversations([newConv, ...conversations]);
        setActiveConvId(newConv.id);
        targetConvId = newConv.id;
      } catch (err) {
        setErrorMsg('Failed to create a conversation thread.');
        return;
      }
    }

    // Add optimistic user message to UI
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: targetConvId,
      user_id: profile?.uid || 'user',
      role: 'user',
      content: prompt,
      created_at: new Date().toISOString(),
      token_count: Math.max(1, Math.floor(prompt.length / 4)),
      retrieved_memory_ids: [],
    };

    setMessages((prev) => [...prev, tempUserMsg]);
    setInputPrompt('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
    setIsLoading(true);
    setStreamingText('');
    setErrorMsg(null);

    // Stream response via SSE
    let accumulated = '';
    await api.streamMessage(
      targetConvId,
      prompt,
      (delta) => {
        accumulated += delta;
        setStreamingText(accumulated);
      },
      async () => {
        setStreamingText('');
        setIsLoading(false);
        if (targetConvId) {
          await loadMessages(targetConvId);
          await loadConversations();
        }
      },
      (err) => {
        console.warn('Streaming failed, falling back to standard REST POST:', err);
        api.sendMessage(targetConvId!, prompt)
          .then((assistantMsg) => {
            setMessages((prev) => [...prev, assistantMsg]);
            loadConversations();
          })
          .catch((postErr: any) => {
            setErrorMsg(postErr?.message || 'Failed to generate assistant response.');
          })
          .finally(() => {
            setStreamingText('');
            setIsLoading(false);
          });
      }
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleExpandMemory = async (msgId: string, memoryIds: string[]) => {
    if (expandedMemoryMsgId === msgId) {
      setExpandedMemoryMsgId(null);
      return;
    }
    setExpandedMemoryMsgId(msgId);

    const toFetch = memoryIds.filter((id) => !memoryDetailsCache[id]);
    for (const memId of toFetch) {
      try {
        const mem = await api.getMemory(memId);
        setMemoryDetailsCache((prev) => ({ ...prev, [memId]: mem }));
      } catch (err) {
        console.warn(`Could not load memory ${memId}:`, err);
      }
    }
  };

  if (authLoading) {
    return (
      <div className="flex-1 h-full flex items-center justify-center p-8 text-slate-400">
        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const activeConv = conversations.find((c) => c.id === activeConvId);

  const filteredConversations = conversations.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 h-full min-h-0 flex flex-row overflow-hidden bg-slate-50 relative">
      
      {/* Threads Sub-Sidebar */}
      <aside
        className={`
          ${threadsOpen ? 'w-64 sm:w-72' : 'w-0'}
          h-full shrink-0 bg-white border-r border-slate-200 transition-all duration-200 flex flex-col overflow-hidden z-20
        `}
      >
        <div className="p-3 border-b border-slate-100 flex flex-col gap-2 shrink-0">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Conversation</span>
          </button>

          {conversations.length > 5 && (
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter threads..."
                className="w-full pl-7 pr-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
              />
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2 top-2" />
            </div>
          )}
        </div>

        {/* Conversation List: Sub-sidebar scrolls independently */}
        <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-0.5">
          {conversations.length === 0 ? (
            <div className="text-center py-12 text-xs text-slate-400 px-4 space-y-1">
              <MessageSquare className="w-6 h-6 text-slate-300 mx-auto" />
              <p className="font-medium text-slate-600">No conversations yet</p>
              <p className="text-[11px]">Click New Conversation to start.</p>
            </div>
          ) : (
            filteredConversations.map((conv) => {
              const isActive = conv.id === activeConvId;
              const isEditing = conv.id === editingConvId;

              return (
                <div
                  key={conv.id}
                  onClick={() => setActiveConvId(conv.id)}
                  className={`
                    group relative flex items-center justify-between px-2.5 py-2 rounded-lg text-xs cursor-pointer transition-colors
                    ${
                      isActive
                        ? 'bg-slate-100 text-slate-900 font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }
                  `}
                >
                  <div className="flex items-center gap-2 min-w-0 flex-1 pr-1">
                    <MessageSquare
                      className={`w-3.5 h-3.5 shrink-0 ${
                        conv.is_pinned ? 'text-amber-500' : isActive ? 'text-indigo-600' : 'text-slate-400'
                      }`}
                    />
                    {isEditing ? (
                      <input
                        type="text"
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                        className="bg-white px-1.5 py-0.5 rounded text-slate-900 text-xs border border-indigo-500 outline-none w-full"
                      />
                    ) : (
                      <span className="truncate">{conv.title}</span>
                    )}
                  </div>

                  {/* Thread Actions */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    {isEditing ? (
                      <>
                        <button
                          onClick={(e) => handleSaveRename(e, conv.id)}
                          className="p-1 hover:text-emerald-600 rounded"
                          title="Save"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingConvId(null);
                          }}
                          className="p-1 hover:text-slate-500 rounded"
                          title="Cancel"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={(e) => handleTogglePin(e, conv)}
                          className={`p-1 hover:text-amber-600 rounded ${conv.is_pinned ? 'text-amber-500' : 'text-slate-400'}`}
                          title={conv.is_pinned ? 'Unpin' : 'Pin conversation'}
                        >
                          <Pin className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => handleStartRename(e, conv)}
                          className="p-1 text-slate-400 hover:text-indigo-600 rounded"
                          title="Rename"
                        >
                          <Edit2 className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => handleDeleteConversation(e, conv.id)}
                          className="p-1 text-slate-400 hover:text-rose-600 rounded"
                          title="Delete"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Conversation Column: strictly full height and non-scrolling except messages area */}
      <section className="flex-1 h-full min-h-0 flex flex-col overflow-hidden bg-slate-50 relative">
        
        {/* Conversation Sub-Header: strictly fixed at top of chat panel */}
        <div className="h-11 shrink-0 px-4 border-b border-slate-200/80 bg-white flex items-center justify-between z-10">
          <div className="flex items-center gap-2 min-w-0">
            <button
              onClick={() => setThreadsOpen(!threadsOpen)}
              className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              title={threadsOpen ? 'Collapse threads' : 'Show threads'}
            >
              {threadsOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
            <span className="font-semibold text-xs sm:text-sm text-slate-900 truncate">
              {activeConv?.title || 'Chat Workspace'}
            </span>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
              {activeConv?.model || 'Gemini 2.5 Flash'}
            </span>
          </div>
        </div>

        {/* Message Feed: THE ONLY VERTICALLY SCROLLABLE AREA */}
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-4 sm:px-6 py-6">
          <div className="max-w-3xl mx-auto space-y-6 pb-6 min-w-0">
            
            {errorMsg && (
              <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
                <button
                  onClick={() => activeConvId && loadMessages(activeConvId)}
                  className="inline-flex items-center gap-1 font-semibold text-rose-700 hover:text-rose-900 underline"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Retry
                </button>
              </div>
            )}

            {/* Empty State */}
            {messages.length === 0 && !isLoading && !streamingText && (
              <div className="py-12 text-center max-w-lg mx-auto space-y-5">
                <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mx-auto shadow-xs">
                  <Brain className="w-6 h-6" />
                </div>
                
                <div className="space-y-1.5">
                  <h2 className="text-base font-semibold text-slate-900">
                    How can I assist you today?
                  </h2>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    Chat naturally with your AI assistant. Critical facts and preferences are selectively
                    retained in long-term memory, while transient conversational chatter decays gracefully.
                  </p>
                </div>

                {/* Prompt Suggestions */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left pt-2">
                  {[
                    'What are my saved critical preferences?',
                    'Deploy Docker container with 3 replicas',
                    'What database infrastructure do we use?',
                    'Summarize what you remember about me',
                  ].map((prompt, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSendMessage(prompt)}
                      className="p-3 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-xs text-slate-700 hover:text-slate-900 transition-all hover:border-indigo-300 shadow-xs"
                    >
                      &ldquo;{prompt}&rdquo;
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((msg) => {
              const isUser = msg.role === 'user';
              const hasRecalledMemories = msg.retrieved_memory_ids && msg.retrieved_memory_ids.length > 0;
              const isExpanded = expandedMemoryMsgId === msg.id;

              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 min-w-0 ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  {/* Assistant Avatar */}
                  {!isUser && (
                    <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 text-indigo-600 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  {/* Bubble Container */}
                  <div className={`space-y-1.5 max-w-[85%] sm:max-w-[80%] min-w-0`}>
                    <div
                      className={`
                        p-4 rounded-2xl text-xs sm:text-sm leading-relaxed break-words [overflow-wrap:anywhere] min-w-0
                        ${
                          isUser
                            ? 'bg-indigo-600 text-white rounded-tr-sm shadow-xs'
                            : 'bg-white text-slate-800 border border-slate-200/80 rounded-tl-sm shadow-xs'
                        }
                      `}
                    >
                      {isUser ? (
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                      ) : (
                        <MarkdownContent content={msg.content} />
                      )}
                    </div>

                    {/* Metadata & Unobtrusive Indicators */}
                    <div
                      className={`flex items-center gap-2 text-[10px] text-slate-400 ${
                        isUser ? 'justify-end' : 'justify-start'
                      }`}
                    >
                      <span>
                        {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                      {msg.token_count > 0 && <span>&bull; ~{msg.token_count} tok</span>}

                      {/* Recalled Memories Indicator */}
                      {!isUser && hasRecalledMemories && (
                        <button
                          onClick={() => handleExpandMemory(msg.id, msg.retrieved_memory_ids)}
                          className="inline-flex items-center gap-1 text-slate-600 hover:text-indigo-600 font-medium bg-slate-100 hover:bg-slate-200/80 border border-slate-200 px-1.5 py-0.5 rounded transition-colors"
                        >
                          <Database className="w-3 h-3 text-indigo-500" />
                          <span>
                            {msg.retrieved_memory_ids.length} recalled
                          </span>
                        </button>
                      )}

                      {/* Saved Memory Indicator */}
                      {!isUser &&
                        msg.metadata?.new_memories_created &&
                        Array.isArray(msg.metadata.new_memories_created) &&
                        msg.metadata.new_memories_created.length > 0 && (
                          <button
                            onClick={() => router.push('/memories')}
                            className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 px-1.5 py-0.5 rounded transition-colors"
                          >
                            <Brain className="w-3 h-3 text-emerald-600" />
                            <span>
                              {msg.metadata.new_memories_created.length} saved
                            </span>
                          </button>
                        )}
                    </div>

                    {/* Expanded Memory Provenance Panel */}
                    {!isUser && isExpanded && (
                      <div className="mt-2 p-3 rounded-xl bg-white border border-slate-200 shadow-sm text-xs space-y-2">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-1.5">
                          <span className="font-semibold text-slate-800 flex items-center gap-1.5 text-xs">
                            <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                            Recalled Cognitive Context
                          </span>
                          <button
                            onClick={() => setExpandedMemoryMsgId(null)}
                            className="text-slate-400 hover:text-slate-600 p-0.5"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>

                        <div className="space-y-1.5 pt-1">
                          {msg.retrieved_memory_ids.map((memId) => {
                            const mem = memoryDetailsCache[memId];
                            return (
                              <div
                                key={memId}
                                className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/60 space-y-1"
                              >
                                <div className="flex items-center justify-between text-[10px]">
                                  <span className="font-bold uppercase text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100">
                                    {mem?.category || 'Memory'}
                                  </span>
                                  <span className="text-slate-500 font-mono">
                                    Score: {mem?.retention_score ? mem.retention_score.toFixed(3) : 'Active'}
                                  </span>
                                </div>
                                <p className="text-slate-700 text-xs leading-relaxed">
                                  {mem ? mem.content : `Loading memory #${memId.slice(0, 8)}...`}
                                </p>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Live Streaming Bubble */}
            {streamingText && (
              <div className="flex gap-3 justify-start min-w-0">
                <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 text-indigo-600 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="space-y-1 max-w-[85%] sm:max-w-[80%] min-w-0">
                  <div className="p-4 rounded-2xl bg-white text-slate-800 border border-indigo-200 rounded-tl-sm shadow-xs text-xs sm:text-sm leading-relaxed break-words [overflow-wrap:anywhere]">
                    <MarkdownContent content={streamingText} />
                    <span className="inline-block w-1.5 h-3.5 bg-indigo-600 ml-1 animate-pulse align-middle" />
                  </div>
                  <span className="text-[10px] text-slate-400">Receiving response...</span>
                </div>
              </div>
            )}

            {/* Loading Indicator */}
            {isLoading && !streamingText && (
              <div className="flex gap-3 justify-start">
                <div className="w-7 h-7 rounded-lg bg-white border border-slate-200 text-indigo-600 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="p-3.5 rounded-2xl bg-white text-slate-500 border border-slate-200 rounded-tl-sm text-xs flex items-center gap-2 shadow-xs">
                  <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
                  <span>Recalling context & querying Gemini...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Message Composer: strictly anchored at the bottom of the chat panel */}
        <div className="p-3 sm:p-4 bg-white border-t border-slate-200 shrink-0 z-10 shadow-xs">
          <div className="max-w-3xl mx-auto">
            <div className="relative flex items-end gap-2 bg-slate-50 rounded-xl p-2 border border-slate-200 focus-within:border-indigo-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-indigo-100 transition-all">
              <textarea
                ref={inputRef}
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Send a message... (Press Enter to send, Shift+Enter for new line)"
                rows={1}
                className="flex-1 bg-transparent border-none text-slate-900 text-xs sm:text-sm px-2 py-1.5 focus:outline-none resize-none max-h-40 min-h-[36px] placeholder:text-slate-400"
              />
              <button
                onClick={() => handleSendMessage()}
                disabled={!inputPrompt.trim() || isLoading}
                className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white transition-colors disabled:opacity-40 disabled:hover:bg-indigo-600 shadow-xs shrink-0"
                title="Send message"
              >
                {isLoading ? (
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <ArrowUp className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="mt-1.5 text-center text-[11px] text-slate-400">
              Shift + Enter for new line. Semantic recall and cognitive forgetting operate automatically.
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
