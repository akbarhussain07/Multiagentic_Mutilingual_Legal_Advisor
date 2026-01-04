import React, { useState, useRef, useEffect } from 'react';
import { Send, Menu, Plus, LogOut, User, Scale, MessageSquare, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import './ChatPage.css';
import { queryLegalQuestion, checkHealth } from './api';

export default function ChatPage() {
  const [message, setMessage] = useState('');
  const [chats, setChats] = useState([{ id: 1, name: 'New Chat', messages: [] }]);
  const [activeChat, setActiveChat] = useState(1);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState('checking');
  const messagesEndRef = useRef(null);
  const [username, setUsername] = useState('Guest');

  // Security check and backend health check
  useEffect(() => {
    const storedName = localStorage.getItem('chatUser');
    const token = localStorage.getItem('authToken');

    if (!token) {
      window.location.href = '/login';
    } else {
      setUsername(storedName || 'User');
      // Check backend health after login verification
      checkBackendHealth();
    }
  }, []);

  // Check backend health status
  const checkBackendHealth = async () => {
    try {
      const health = await checkHealth();
      if (health.status === 'healthy' && health.neo4j_connected && health.documents_loaded) {
        setBackendStatus('connected');
      } else {
        setBackendStatus('disconnected');
      }
    } catch (error) {
      console.error('Backend health check failed:', error);
      setBackendStatus('disconnected');
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading || backendStatus !== 'connected') return;

    const userMessage = {
      id: Date.now(),
      type: 'user',
      content: message,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    const questionText = message;
    setMessage('');
    setIsLoading(true);

    try {
      // Call the Django backend API
      const response = await queryLegalQuestion(questionText);
      
      const botMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: response.answer || 'I apologize, but I could not generate a response.',
        sources: response.sources || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      
      setMessages(prev => [...prev, botMessage]);
      
      // Update chat title with first message
      if (newMessages.length === 1) {
        setChats(prev => prev.map(chat =>
          chat.id === activeChat
            ? { ...chat, name: questionText.slice(0, 30) + (questionText.length > 30 ? '...' : ''), messages: [...newMessages, botMessage] }
            : chat
        ));
      } else {
        // Update existing chat messages
        setChats(prev => prev.map(chat =>
          chat.id === activeChat
            ? { ...chat, messages: [...newMessages, botMessage] }
            : chat
        ));
      }
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        id: Date.now() + 1,
        type: 'bot',
        content: 'I apologize, but I encountered an error connecting to the backend. Please ensure the Django server is running on http://localhost:8000.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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
    const newId = Date.now();
    setChats([...chats, { id: newId, name: 'New Chat', messages: [] }]);
    setActiveChat(newId);
    setMessages([]);
  };

  const switchChat = (id) => {
    setActiveChat(id);
    const chat = chats.find(c => c.id === id);
    setMessages(chat ? chat.messages : []);
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
          {chats.map((chat) => (
            <button
              key={chat.id}
              className={`chat-item ${activeChat === chat.id ? 'active' : ''}`}
              onClick={() => switchChat(chat.id)}
            >
              <MessageSquare size={16} />
              <span className="chat-title">{chat.name}</span>
            </button>
          ))}
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
          
          {/* Backend Status Indicator */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
            {backendStatus === 'connected' && (
              <>
                <CheckCircle size={16} color="#10b981" />
                <span style={{ fontSize: '14px', color: '#10b981' }}>Connected</span>
              </>
            )}
            {backendStatus === 'disconnected' && (
              <>
                <AlertCircle size={16} color="#ef4444" />
                <span style={{ fontSize: '14px', color: '#ef4444' }}>Offline</span>
              </>
            )}
            {backendStatus === 'checking' && (
              <>
                <Loader2 size={16} color="#f59e0b" className="spinner" />
                <span style={{ fontSize: '14px', color: '#f59e0b' }}>Connecting...</span>
              </>
            )}
          </div>
        </header>

        {/* Chat Area */}
        <section className="chat-area">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Scale size={40} color="white" />
              </div>
              <h2 className="welcome-title">How can I help you today?</h2>
              <p className="welcome-subtitle">
                Ask me anything about the Pakistani Constitution. I'll provide accurate
                answers based on official documents.
              </p>
            </div>
          ) : (
            <div className="messages-container">
              {messages.map((msg) => (
                <div key={msg.id} className={`message-wrapper ${msg.type}`}>
                  {msg.type === 'bot' && (
                    <div className="bot-avatar">
                      <Scale size={20} color="white" />
                    </div>
                  )}
                  <div className={`message-bubble ${msg.type}`}>
                    <p className="message-text">{msg.content}</p>
                    {msg.sources && msg.sources.length > 0 && (
                      <div style={{ 
                        marginTop: '12px', 
                        paddingTop: '12px', 
                        borderTop: '1px solid #e0e0e0',
                        fontSize: '12px',
                        color: '#666'
                      }}>
                        <strong>Sources:</strong>
                        {msg.sources.map((source, idx) => (
                          <div key={idx} style={{ marginTop: '4px', paddingLeft: '8px' }}>
                            • {source.content}
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
              
              {/* Loading indicator */}
              {isLoading && (
                <div className="message-wrapper bot">
                  <div className="bot-avatar">
                    <Scale size={20} color="white" />
                  </div>
                  <div className="message-bubble bot">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Loader2 size={16} className="spinner" />
                      <span>Thinking...</span>
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