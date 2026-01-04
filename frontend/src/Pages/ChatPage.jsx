import React, { useState, useRef, useEffect } from 'react';
import { Send, Menu, Plus, LogOut, User, Scale, MessageSquare, Loader2, AlertCircle, CheckCircle, Trash2 } from 'lucide-react';
import './ChatPage.css';
import { queryLegalQuestion, checkHealth, getUserSessions, getSessionMessages, deleteChatSession } from './api';

export default function ChatPage() {
  const [message, setMessage] = useState('');
  
  // 'chats' now only stores the Sidebar list (id, title)
  const [chats, setChats] = useState([]); 
  
  // 'activeChat' stores the UUID of the current session, or 'new'
  const [activeChat, setActiveChat] = useState('new'); 
  
  // 'messages' stores the content of the CURRENT active chat
  const [messages, setMessages] = useState([]);
  
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false); // For sidebar loading
  const [backendStatus, setBackendStatus] = useState('checking');
  const messagesEndRef = useRef(null);
  const [username, setUsername] = useState('Guest');

  // 1. Initial Setup: Check Auth, Health, and Load Sidebar History
  useEffect(() => {
    const storedName = localStorage.getItem('chatUser');
    const token = localStorage.getItem('authToken');

    if (!token) {
      window.location.href = '/login';
    } else {
      setUsername(storedName || 'User');
      checkBackendHealth();
      loadSidebarHistory();
    }
  }, []);

  // 2. Load Messages when Active Chat Changes
  useEffect(() => {
    if (activeChat === 'new') {
      setMessages([]);
    } else {
      loadChatMessages(activeChat);
    }
  }, [activeChat]);

  // Auto-scroll to bottom
  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // --- API Interaction Functions ---
  const handleDeleteChat = async (e, sessionId) => {
    e.stopPropagation(); // Prevents the chat from opening when you click delete
    
    if (!window.confirm("Are you sure you want to delete this chat?")) return;

    try {
      await deleteChatSession(sessionId);
      
      setChats(prev => prev.filter(chat => chat.id !== sessionId));

      // If we deleted the currently active chat, switch to New Chat
      if (activeChat === sessionId) {
        handleNewChat();
      }
    } catch (error) {
      console.error("Failed to delete chat:", error);
      alert("Could not delete chat. Please try again.");
    }
  };


  const checkBackendHealth = async () => {
    try {
      const health = await checkHealth();
      if (health.status === 'healthy' && health.neo4j_connected) {
        setBackendStatus('connected');
      } else {
        setBackendStatus('disconnected');
      }
    } catch (error) {
      console.error('Backend health check failed:', error);
      setBackendStatus('disconnected');
    }
  };

  const loadSidebarHistory = async () => {
    setIsHistoryLoading(true);
    try {
      const sessions = await getUserSessions();
      setChats(sessions); // Expecting array of { id, name, updated_at }
    } catch (error) {
      console.error("Failed to load history:", error);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  const loadChatMessages = async (sessionId) => {
    setIsLoading(true); // Reuse loading state or create a specific one for fetching
    try {
      const msgs = await getSessionMessages(sessionId);
      // Backend returns: { type: 'user'|'bot', content: '...', timestamp: '...' }
      // We need to add local IDs for React keys if the backend doesn't provide unique IDs for rendering
      const formattedMsgs = msgs.map((msg, index) => ({
        ...msg,
        id: index // Simple index for display key, ideally backend sends UUID
      }));
      setMessages(formattedMsgs);
    } catch (error) {
      console.error("Failed to load messages:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading || backendStatus !== 'connected') return;

    const currentQuestion = message;
    setMessage('');
    
    // Optimistic UI Update: Show user message immediately
    const tempUserMsg = {
      id: Date.now(),
      type: 'user',
      content: currentQuestion,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setIsLoading(true);

    try {
      // Determine Session ID (null if new, uuid if existing)
      const sessionIdToSend = activeChat === 'new' ? null : activeChat;

      // Call Backend
      const response = await queryLegalQuestion(currentQuestion, sessionIdToSend);
      
      const botMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: response.answer || 'No response generated.',
        sources: response.sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      
      setMessages(prev => [...prev, botMessage]);

      // CRITICAL: If we started a NEW chat, the backend created a session. 
      // We must switch to that ID and refresh the sidebar.
      if (activeChat === 'new' && response.session_id) {
        setActiveChat(response.session_id); // This will NOT trigger re-fetch due to logic check? Actually it might.
        // To prevent re-fetching messages we just displayed, we could optimize, 
        // but for now, let's just refresh the sidebar title.
        loadSidebarHistory(); 
      }

    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 2,
        type: 'bot',
        content: 'Error: Could not connect to the Legal Advisor backend.',
        timestamp: new Date().toLocaleTimeString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewChat = () => {
    setActiveChat('new');
    setMessages([]);
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('chatUser');
    window.location.href = '/login';
  };

  return (
    <div className="chat-page-container">
      {/* Sidebar */}
      <aside className={`sidebar ${!sidebarOpen ? 'closed' : ''}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={handleNewChat}>
            <Plus size={20} />
            New Chat
          </button>
        </div>

        <div className="chat-list">
          {isHistoryLoading ? (
             <div style={{padding: '20px', textAlign: 'center', color: '#666'}}>
               <Loader2 size={20} className="spinner" />
             </div>
          ) : (
            chats.map((chat) => (
              <div 
                key={chat.id} 
                className={`chat-item-wrapper ${activeChat === chat.id ? 'active' : ''}`}
                onClick={() => setActiveChat(chat.id)}
              >
                <button className="chat-item-content">
                  <MessageSquare size={16} />
                  <span className="chat-title">{chat.name || 'Untitled Chat'}</span>
                </button>
                
                {/* 4. The Delete Button */}
                <button 
                  className="delete-chat-btn"
                  onClick={(e) => handleDeleteChat(e, chat.id)}
                  title="Delete Chat"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">
              <User size={20} color="white" />
            </div>
            <span className="username">{username}</span>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {/* Header */}
        <header className="chat-header">
          <button className="menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            <Menu size={24} />
          </button>
          <h1 className="app-title">
            <div className="bot-avatar">
              <Scale size={18} color="white" />
            </div>
            Legal Advisor
          </h1>
          
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {backendStatus === 'connected' ? (
              <>
                <CheckCircle size={16} color="#10b981" />
                <span style={{ fontSize: '14px', color: '#10b981' }}>Connected</span>
              </>
            ) : backendStatus === 'disconnected' ? (
              <>
                <AlertCircle size={16} color="#ef4444" />
                <span style={{ fontSize: '14px', color: '#ef4444' }}>Offline</span>
              </>
            ) : (
              <>
                <Loader2 size={16} color="#f59e0b" className="spinner" />
                <span style={{ fontSize: '14px', color: '#f59e0b' }}>Connecting...</span>
              </>
            )}
          </div>
        </header>

        {/* Chat Area */}
        <section className="chat-area">
          {messages.length === 0 && activeChat === 'new' ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Scale size={40} color="white" />
              </div>
              <h2 className="welcome-title">How can I help you today?</h2>
              <p className="welcome-subtitle">
                Ask me anything about the Pakistani or Islamic Laws. I will provide accurate
                answers based on official documents.
              </p>
            </div>
          ) : (
            <div className="messages-container">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message-wrapper ${msg.type}`}>
                  {msg.type === 'bot' && (
                    <div className="bot-avatar">
                      <Scale size={20} color="white" />
                    </div>
                  )}
                  <div className={`message-bubble ${msg.type}`}>
                    <p className="message-text">{msg.content}</p>
                    
                    {/* Render Sources if available */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="message-sources">
                        <strong>Sources:</strong>
                        {msg.sources.map((source, sIdx) => (
                          <div key={sIdx} className="source-item">
                            • {source.content || source}
                          </div>
                        ))}
                      </div>
                    )}
                    
                    <span className={`message-time ${msg.type}`}>
                      {msg.timestamp}
                    </span>
                  </div>
                  {msg.type === 'user' && (
                    <div className="user-avatar-msg">
                      <User size={20} color="#666" />
                    </div>
                  )}
                </div>
              ))}
              
              {isLoading && (
                <div className="message-wrapper bot">
                  <div className="bot-avatar">
                    <Scale size={20} color="white" />
                  </div>
                  <div className="message-bubble bot">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Loader2 size={16} className="spinner" />
                      <span>Analyzing legal documents...</span>
                    </div>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>
          )}
        </section>

        {/* Input Area */}
        <footer className="input-area">
          <div className="input-wrapper">
            <div className="input-container">
              <input
                type="text"
                className="message-input"
                placeholder="Ask a legal question..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isLoading || backendStatus !== 'connected'}
              />
              <button
                className={`send-btn ${message.trim() && !isLoading && backendStatus === 'connected' ? 'active' : ''}`}
                onClick={handleSendMessage}
                disabled={!message.trim() || isLoading || backendStatus !== 'connected'}
              >
                {isLoading ? <Loader2 size={20} className="spinner" /> : <Send size={20} />}
              </button>
            </div>
            {backendStatus === 'disconnected' && (
              <p className="server-status">
                Backend server is offline. Please start Django server on http://localhost:8000
              </p>
            )}
          </div>
        </footer>
      </main>
    </div>
  );
}