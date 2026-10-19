import React, { useState, useEffect, useRef } from 'react';
import {
  MessageSquare,
  Plus,
  Send,
  Trash2,
  Pin,
  Sparkles,
  Brain,
  ShieldCheck,
  User,
  Settings,
  LogOut,
  ChevronRight,
  Database,
  Cpu
} from 'lucide-react';
import { api, Conversation, ChatMessage, UserRecord } from '../api';

interface ChatViewProps {
  user: UserRecord | null;
  onOpenSettings: () => void;
  onOpenAdmin: () => void;
  onOpenMemories: () => void;
  onLogout: () => void;
}

export const ChatView: React.FC<ChatViewProps> = ({
  user,
  onOpenSettings,
  onOpenAdmin,
  onOpenMemories,
  onLogout,
}) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (activeConvId) {
      loadMessages(activeConvId);
    } else {
      setMessages([]);
    }
  }, [activeConvId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const loadConversations = async () => {
    try {
      const data = await api.listConversations();
      setConversations(data);
      if (data.length > 0 && !activeConvId) {
        setActiveConvId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load conversations:', err);
    }
  };

  const loadMessages = async (convId: string) => {
    try {
      const msgs = await api.getMessages(convId);
      setMessages(msgs);
    } catch (err) {
      console.error('Failed to load messages:', err);
    }
  };

  const handleNewChat = async () => {
    try {
      const newConv = await api.createConversation('New Conversation');
      setConversations([newConv, ...conversations]);
      setActiveConvId(newConv.id);
      setMessages([]);
    } catch (err) {
      console.error('Failed to create new conversation:', err);
    }
  };

  const handleDeleteConversation = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this conversation?')) return;
    try {
      await api.deleteConversation(id);
      const updated = conversations.filter((c) => c.id !== id);
      setConversations(updated);
      if (activeConvId === id) {
        setActiveConvId(updated.length > 0 ? updated[0].id : null);
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputPrompt.trim() || isLoading) return;

    let targetConvId = activeConvId;
    if (!targetConvId) {
      try {
        const newConv = await api.createConversation(inputPrompt.slice(0, 30));
        setConversations([newConv, ...conversations]);
        targetConvId = newConv.id;
        setActiveConvId(newConv.id);
      } catch (err) {
        console.error('Failed to auto-create conversation:', err);
        return;
      }
    }

    const currentText = inputPrompt;
    setInputPrompt('');
    setIsLoading(true);

    // Optimistic user message
    const tempUserMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: targetConvId,
      user_id: user?.uid || 'user',
      role: 'user',
      content: currentText,
      created_at: new Date().toISOString(),
      token_count: Math.ceil(currentText.length / 4),
      retrieved_memory_ids: [],
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const assistantMsg = await api.sendMessage(targetConvId, currentText);
      setMessages((prev) => [...prev.filter((m) => m.id !== tempUserMsg.id), tempUserMsg, assistantMsg]);
      loadConversations(); // refresh updated_at and titles
    } catch (err: any) {
      console.error('Error sending message:', err);
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        conversation_id: targetConvId,
        user_id: 'system',
        role: 'assistant',
        content: `⚠️ Error: ${err.message || 'Unable to connect to AI Inference Service.'}`,
        created_at: new Date().toISOString(),
        token_count: 0,
        retrieved_memory_ids: [],
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const promptSuggestions = [
    "My name is Arun. I am studying computer science and researching agentic AI memory.",
    "Help me prepare my project presentation.",
    "What do you remember about my identity and preferences?",
    "Always enforce PostgreSQL connection pooling and strict unit testing."
  ];

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden', backgroundColor: 'var(--bg-primary)' }}>
      {/* LEFT SIDEBAR */}
      <div
        style={{
          width: sidebarOpen ? '280px' : '0px',
          transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          overflow: 'hidden',
          backgroundColor: 'var(--bg-secondary)',
          borderRight: '1px solid var(--border-color)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 20,
        }}
      >
        <div style={{ padding: '16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Brain size={18} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#fff' }}>Intelligent AI</div>
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Cognitive Memory Agent</div>
            </div>
          </div>
        </div>

        {/* New Chat Button */}
        <div style={{ padding: '12px 16px' }}>
          <button className="btn btn-primary" onClick={handleNewChat} style={{ width: '100%', justifyContent: 'flex-start' }}>
            <Plus size={16} />
            <span>New Chat</span>
          </button>
        </div>

        {/* Navigation links for Memory & Admin */}
        <div style={{ padding: '0 16px 8px 16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <button
            className="btn btn-secondary"
            onClick={onOpenMemories}
            style={{ width: '100%', justifyContent: 'flex-start', fontSize: '0.8rem', padding: '6px 12px' }}
          >
            <Database size={15} color="#22d3ee" />
            <span>Memory Manager</span>
          </button>
          {user?.role === 'admin' && (
            <button
              className="btn btn-secondary"
              onClick={onOpenAdmin}
              style={{ width: '100%', justifyContent: 'flex-start', fontSize: '0.8rem', padding: '6px 12px', borderColor: 'rgba(99, 102, 241, 0.4)' }}
            >
              <ShieldCheck size={15} color="#818cf8" />
              <span>Admin Dashboard</span>
            </button>
          )}
        </div>

        {/* Conversations List */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
          <div style={{ fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-sub)', textTransform: 'uppercase', padding: '6px 8px' }}>
            Conversations
          </div>
          {conversations.length === 0 ? (
            <div style={{ padding: '16px 8px', fontSize: '0.8rem', color: 'var(--text-sub)', textAlign: 'center' }}>
              No chats yet. Start a new one!
            </div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                onClick={() => setActiveConvId(conv.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-md)',
                  marginBottom: '4px',
                  cursor: 'pointer',
                  backgroundColor: activeConvId === conv.id ? 'var(--bg-tertiary)' : 'transparent',
                  border: activeConvId === conv.id ? '1px solid var(--border-focus)' : '1px solid transparent',
                  color: activeConvId === conv.id ? '#fff' : 'var(--text-muted)',
                  fontSize: '0.85rem',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <MessageSquare size={14} color={activeConvId === conv.id ? 'var(--primary)' : 'var(--text-sub)'} />
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }}>
                    {conv.title}
                  </span>
                </div>
                <button
                  onClick={(e) => handleDeleteConversation(e, conv.id)}
                  style={{ background: 'none', border: 'none', color: 'var(--text-sub)', cursor: 'pointer', padding: '2px', opacity: 0.6 }}
                  title="Delete conversation"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* User Footer Card */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-color)', backgroundColor: 'rgba(15, 23, 42, 0.95)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: 'var(--primary-light)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <User size={16} color="var(--primary)" />
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fff', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user?.display_name || 'User'}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-sub)', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                  {user?.role === 'admin' ? 'Administrator' : 'Standard User'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                onClick={onOpenSettings}
                className="btn btn-secondary btn-sm"
                style={{ padding: '6px' }}
                title="Settings & Privacy"
              >
                <Settings size={14} />
              </button>
              <button
                onClick={onLogout}
                className="btn btn-secondary btn-sm"
                style={{ padding: '6px' }}
                title="Log Out"
              >
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* MAIN CHAT AREA */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
        {/* Top Header */}
        <div
          style={{
            height: '56px',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 20px',
            backgroundColor: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
            >
              <MessageSquare size={18} />
            </button>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>
              {conversations.find((c) => c.id === activeConvId)?.title || 'AI Chat Assistant'}
            </div>
            <span className="badge badge-active" style={{ fontSize: '0.65rem' }}>
              <Sparkles size={10} /> Gemini 2.5 Flash
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              <Cpu size={14} color="var(--primary)" />
              <span>Cognitive Memory: Active</span>
            </div>
          </div>
        </div>

        {/* Message Stream */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {messages.length === 0 ? (
            <div style={{ margin: 'auto', maxWidth: '640px', textAlign: 'center', padding: '30px 20px' }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '16px', background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(6, 182, 212, 0.2))', border: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                <Sparkles size={28} color="var(--primary)" />
              </div>
              <h2 style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '8px' }}>
                Intelligent Memory AI Chat
              </h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px', lineHeight: 1.5 }}>
                Chat with an AI agent equipped with continuous intelligent forgetting. The system automatically extracts,
                retains, compresses, or prunes memories based on multi-factor cognitive utility.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', textAlign: 'left' }}>
                {promptSuggestions.map((prompt, idx) => (
                  <div
                    key={idx}
                    onClick={() => {
                      setInputPrompt(prompt);
                    }}
                    className="glass-panel"
                    style={{
                      padding: '12px',
                      cursor: 'pointer',
                      fontSize: '0.8rem',
                      color: 'var(--text-muted)',
                      border: '1px solid var(--border-color)',
                      transition: 'all 0.15s ease',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'var(--primary)')}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-color)')}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fff', fontWeight: 500, marginBottom: '4px' }}>
                      <Sparkles size={12} color="var(--accent)" /> Example
                    </div>
                    {prompt}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div
                  style={{
                    maxWidth: '75%',
                    borderRadius: '16px',
                    padding: '14px 18px',
                    fontSize: '0.9rem',
                    lineHeight: 1.6,
                    backgroundColor: msg.role === 'user' ? 'var(--primary)' : 'var(--bg-secondary)',
                    color: '#ffffff',
                    border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)',
                    boxShadow: 'var(--shadow-md)',
                  }}
                >
                  {/* Retrieved memory indicators */}
                  {msg.role === 'assistant' && msg.retrieved_memory_ids && msg.retrieved_memory_ids.length > 0 && (
                    <div
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        background: 'rgba(99, 102, 241, 0.15)',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        borderRadius: 'var(--radius-full)',
                        padding: '3px 10px',
                        fontSize: '0.72rem',
                        color: '#a5b4fc',
                        marginBottom: '10px',
                      }}
                    >
                      <Brain size={12} color="#818cf8" />
                      <span>Informed by {msg.retrieved_memory_ids.length} retrieved memories</span>
                    </div>
                  )}

                  <div className="markdown-content" style={{ whiteSpace: 'pre-wrap' }}>
                    {msg.content}
                  </div>

                  <div style={{ fontSize: '0.65rem', color: msg.role === 'user' ? 'rgba(255,255,255,0.7)' : 'var(--text-sub)', marginTop: '8px', textAlign: 'right' }}>
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </div>
            ))
          )}

          {isLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <div
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '16px',
                  padding: '14px 18px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  color: 'var(--text-muted)',
                  fontSize: '0.85rem',
                }}
              >
                <div className="animate-pulse-glow" style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--primary)' }} />
                <span>Gemini is evaluating memories and synthesizing response...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Bottom Input Area */}
        <div style={{ padding: '16px 24px', backgroundColor: 'var(--bg-secondary)', borderTop: '1px solid var(--border-color)' }}>
          <form
            onSubmit={handleSendMessage}
            style={{
              display: 'flex',
              gap: '10px',
              maxWidth: '900px',
              margin: '0 auto',
              alignItems: 'flex-end',
            }}
          >
            <textarea
              className="input-field"
              rows={2}
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage();
                }
              }}
              placeholder="Type your message... (Shift+Enter for newline)"
              style={{ resize: 'none', padding: '12px 16px' }}
            />
            <button
              type="submit"
              disabled={isLoading || !inputPrompt.trim()}
              className="btn btn-primary"
              style={{ height: '48px', padding: '0 20px', borderRadius: 'var(--radius-md)' }}
            >
              <Send size={16} />
              <span>Send</span>
            </button>
          </form>
          <div style={{ textAlign: 'center', fontSize: '0.7rem', color: 'var(--text-sub)', marginTop: '8px' }}>
            Protected with tenant memory isolation. Outdated and low-value information is intelligently archived or pruned.
          </div>
        </div>
      </div>
    </div>
  );
};
