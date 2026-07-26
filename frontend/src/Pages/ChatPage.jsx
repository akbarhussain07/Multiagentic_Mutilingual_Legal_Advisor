import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "./ChatPage.css";
import {
  Send,
  Menu,
  Plus,
  LogOut,
  User,
  Scale,
  MessageSquare,
  Loader2,
  AlertCircle,
  CheckCircle,
  Trash2,
} from "lucide-react";
import {
  queryLegalQuestion,
  checkHealth,
  getUserSessions,
  getSessionMessages,
  deleteChatSession,
  updateUserProfile,
  deleteUserProfile,
  submitGlobalRating,
} from "./api";

function InlineMarkdown({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }
    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function StructuredText({ content }) {
  const lines = String(content || "No response generated.").split("\n");
  return (
    <div className="structured-answer">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return <div className="answer-spacer" key={index} />;
        if (trimmed.startsWith("### ")) return <h4 key={index}><InlineMarkdown text={trimmed.slice(4)} /></h4>;
        if (trimmed.startsWith("## ")) return <h3 key={index}><InlineMarkdown text={trimmed.slice(3)} /></h3>;
        if (trimmed.startsWith("# ")) return <h2 key={index}><InlineMarkdown text={trimmed.slice(2)} /></h2>;
        if (/^[-*] /.test(trimmed)) return <div className="answer-list-item" key={index}><span>•</span><p><InlineMarkdown text={trimmed.slice(2)} /></p></div>;
        const numbered = trimmed.match(/^(\d+)\.\s+(.+)$/);
        if (numbered) return <div className="answer-list-item" key={index}><span>{numbered[1]}.</span><p><InlineMarkdown text={numbered[2]} /></p></div>;
        return <p key={index}><InlineMarkdown text={trimmed} /></p>;
      })}
    </div>
  );
}

export default function ChatPage() {
  const [message, setMessage] = useState("");

  // 'chats' now only stores the Sidebar list (id, title)
  const [chats, setChats] = useState([]);

  // 'activeChat' stores the UUID of the current session, or 'new'
  const [activeChat, setActiveChat] = useState("new");

  // 'messages' stores the content of the CURRENT active chat
  const [messages, setMessages] = useState([]);

  // Selects exactly one Pinecone legal index per query.
  const [viewMode, setViewMode] = useState("pakistani");

  const suggestedQuestions = {
    pakistani: [
      "What documents are required to transfer property in Pakistan?",
      "How can I challenge an incorrect land mutation entry?",
    ],
    islamic: [
      "How is inherited property divided among Islamic heirs?",
      "What makes a gift of property (hiba) valid in Islamic law?",
    ],
    procedure: [
      "What steps are involved in filing a property ownership case?",
      "Which documents should I prepare for a property dispute?",
    ],
  };

  // 'sidebarOpen' ,manages the side bar open or close
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false); // For sidebar loading
  const [backendStatus, setBackendStatus] = useState("checking");
  const messagesEndRef = useRef(null);
  const [username, setUsername] = useState("Guest");
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [email, setEmail] = useState(localStorage.getItem("userEmail") || "");
  const [editData, setEditData] = useState({
    username: localStorage.getItem("chatUser") || "",
    email: localStorage.getItem("userEmail") || "",
    password: "",
  });
  const [userRating, setUserRating] = useState(0);
  const navigate = useNavigate();
  // Initial Setup: Check Auth, Health, and Load Sidebar History
  useEffect(() => {
    const storedName = localStorage.getItem("chatUser");
    const storedEmail = localStorage.getItem("userEmail");
    const token = localStorage.getItem("authToken");

    if (!token) {
      window.location.href = "/login";
    } else {
      setUsername(storedName || "User");
      setEmail(storedEmail || "");
      checkBackendHealth();
      loadSidebarHistory();
    }
  }, []);
  // Load user Rating
  useEffect(() => {
    const storedRating = localStorage.getItem("userRating");
    // If storedRating is null, we set to 0.
    const initialRating = storedRating ? parseInt(storedRating, 10) : 0;
    setUserRating(initialRating);
  }, []);
  //  Load Messages when Active Chat Changes
  useEffect(() => {
    if (activeChat === "new") {
      setMessages([]);
    } else {
      loadChatMessages(activeChat);
    }
  }, [activeChat]);

  // Auto-scroll to bottom
  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Track mobile breakpoint & auto-close sidebar on mobile
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth <= 768;
      setIsMobile(mobile);
      if (mobile) {
        setSidebarOpen(false); // Start closed on mobile like ChatGPT
      }
    };
    // Set initial state
    if (window.innerWidth <= 768) setSidebarOpen(false);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  //  API Interaction Functions
  const handleDeleteChat = async (e, sessionId) => {
    e.stopPropagation(); // Prevents the chat from opening when you click delete

    if (!window.confirm("Are you sure you want to delete this chat?")) return;

    try {
      await deleteChatSession(sessionId);

      setChats((prev) => prev.filter((chat) => chat.id !== sessionId));

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
      if (health.status === "healthy" && health.pinecone_connected) {
        setBackendStatus("connected");
      } else {
        setBackendStatus("disconnected");
      }
    } catch (error) {
      console.error("Backend health check failed:", error);
      setBackendStatus("disconnected");
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
        id: index, // Simple index for display key, ideally backend sends UUID
      }));
      setMessages(formattedMsgs);
    } catch (error) {
      console.error("Failed to load messages:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (questionOverride = null) => {
    const outgoingQuestion = typeof questionOverride === "string" ? questionOverride : message;
    if (!outgoingQuestion.trim() || isLoading || backendStatus !== "connected") return;

    const currentQuestion = outgoingQuestion.trim();
    setMessage("");

    // Optimistic UI Update: Show user message immediately
    const tempUserMsg = {
      id: Date.now(),
      type: "user",
      content: currentQuestion,
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setIsLoading(true);

    try {
      // Determine Session ID (null if new, uuid if existing)
      const sessionIdToSend = activeChat === "new" ? null : activeChat;

      // Call Backend
      const response = await queryLegalQuestion(
        currentQuestion,
        sessionIdToSend,
        viewMode,
      );

      const botMessage = {
        id: Date.now() + 1,
        type: "bot",
        content: response.answer || "No response generated.",
        pakistanContent: response.pakistanContent,
        islamicContent: response.islamicContent,
        procedureContent: response.procedureContent,
        viewMode,
        sources: response.sources || [],
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };

      setMessages((prev) => [...prev, botMessage]);

      // CRITICAL: If we started a NEW chat, the backend created a session.
      // We must switch to that ID and refresh the sidebar.
      if (activeChat === "new" && response.session_id) {
        setActiveChat(response.session_id); // This will NOT trigger re-fetch due to logic check? Actually it might.
        // To prevent re-fetching messages we just displayed, we could optimize,
        // but for now, let's just refresh the sidebar title.
        loadSidebarHistory();
      }
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage = {
        id: Date.now() + 2,
        type: "bot",
        content: "Error: Could not connect to the Legal Advisor backend.",
        timestamp: new Date().toLocaleTimeString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !isLoading) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleNewChat = () => {
    setActiveChat("new");
    setMessages([]);
  };

  const handleLogout = () => {
    localStorage.removeItem("authToken");
    localStorage.removeItem("chatUser");
    localStorage.removeItem("chatEmail");
    window.location.href = "/login";
  };

  const handleDeleteAccount = async () => {
    const confirm = window.confirm(
      "Are you sure? This will delete your account and all chat history permanently.",
    );
    if (confirm) {
      try {
        const userId = localStorage.getItem("userId");
        if (!userId) {
          alert("User ID not found. Please log in again.");
          return;
        }

        await deleteUserProfile(userId);

        localStorage.clear();
        navigate("/login");
      } catch (err) {
        console.error("Delete Error:", err);
        alert("Could not delete account.");
      }
    }
  };

  const handleUpdateAccount = async (e) => {
    e.preventDefault();
    try {
      const userId = localStorage.getItem("userId");
      const updated = await updateUserProfile(userId, editData);

      // Update local state and storage with the correct keys returned by backend
      setUsername(updated.username);
      localStorage.setItem("chatUser", updated.username);
      setEmail(updated.email);
      localStorage.setItem("chatEmail", updated.email);

      setEditData({
        ...editData,
        username: updated.username,
        email: updated.email,
        password: "",
      });

      setIsProfileModalOpen(false);
      alert("Profile Updated!");
    } catch (err) {
      alert("Update failed.");
    }
  };

  return (
    <div className="chat-page-container">
      {/* Mobile overlay — closes sidebar when tapped outside */}
      {isMobile && sidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${!sidebarOpen ? "closed" : ""}`}>
        <div className="sidebar-header">
          <button
            className="new-chat-btn"
            onClick={() => {
              handleNewChat();
              if (isMobile) setSidebarOpen(false);
            }}
          >
            <Plus size={20} />
            New Chat
          </button>
        </div>

        <div className="chat-list">
          {isHistoryLoading ? (
            <div
              style={{ padding: "20px", textAlign: "center", color: "#666" }}
            >
              <Loader2 size={20} className="spinner" />
            </div>
          ) : (
            chats.map((chat) => (
              <div
                key={chat.id}
                className={`chat-item-wrapper ${activeChat === chat.id ? "active" : ""}`}
                onClick={() => {
                  setActiveChat(chat.id);
                  if (isMobile) setSidebarOpen(false);
                }}
              >
                <button className="chat-item-content">
                  <MessageSquare size={16} />
                  <span className="chat-title">
                    {chat.name || "Untitled Chat"}
                  </span>
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
        {/* Inside <aside className="sidebar">, right above <div className="sidebar-footer"> */}
        {userRating === 0 && (
          <div className="sidebar-feedback-box">
            <span className="feedback-label">Rate your experience:</span>
            <div className="global-stars">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  className={`global-star-btn ${userRating >= star ? "active" : ""}`}
                  // Add "async" here to allow the use of "await" inside the function
                  onClick={async () => {
                    try {
                      // Save to PostgreSQL via the new API
                      await submitGlobalRating(star);
                      // 2. Update Local Storage so it stays hidden after refresh
                      localStorage.setItem("userRating", star.toString());
                      // Update UI immediately
                      setUserRating(star);
                      // Optional: Show a small success toast or silent confirmation
                      alert(
                        `Thank you! Your ${star}-star rating has been saved.`,
                      );
                    } catch (error) {
                      console.error("Rating Error:", error);
                      alert(
                        "Could not save rating. Please check your connection.",
                      );
                    }
                  }}
                >
                  <Scale
                    size={18}
                    fill={userRating >= star ? "currentColor" : "none"}
                  />
                </button>
              ))}
            </div>
          </div>
        )}
        <div
          className="sidebar-footer"
          onClick={() => setIsProfileModalOpen(true)}
          style={{ cursor: "pointer" }}
        >
          <div className="user-info">
            <div className="user-avatar">
              <User size={20} color="white" />
            </div>
            <span className="username">{username}</span>
          </div>
          <div className="settings-hint"> ⚙️</div>
        </div>

        {/* Profile & Settings Modal */}
        {isProfileModalOpen && (
          <div className="modal-overlay">
            <div className="modal-content">
              <div className="modal-header">
                <h3>Account Settings</h3>
                <button
                  className="cross-btn"
                  onClick={() => setIsProfileModalOpen(false)}
                >
                  ×
                </button>
              </div>

              <form onSubmit={handleUpdateAccount}>
                <div className="input-group">
                  <label>Username</label>
                  <input
                    type="text"
                    value={editData.username}
                    onChange={(e) =>
                      setEditData({ ...editData, username: e.target.value })
                    }
                  />
                </div>
                <div className="input-group">
                  <label>Email Address</label>
                  <input
                    type="email"
                    placeholder="Update email..."
                    value={editData.email}
                    onChange={(e) =>
                      setEditData({ ...editData, email: e.target.value })
                    }
                  />
                </div>
                <div className="input-group">
                  <label>New Password</label>
                  <input
                    type="password"
                    placeholder="Leave blank to keep current"
                    onChange={(e) =>
                      setEditData({ ...editData, password: e.target.value })
                    }
                  />
                </div>

                <div className="modal-actions-column">
                  <button type="submit" className="save-btn">
                    Update Profile
                  </button>
                  <button
                    type="button"
                    className="logout-btn-modal"
                    onClick={handleLogout}
                  >
                    Logout
                  </button>
                  <button
                    type="button"
                    className="del-btn"
                    onClick={handleDeleteAccount}
                  >
                    Delete Account
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="main-content">
        {/* Header */}
        <header className="chat-header">
          <button
            className="menu-btn"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            <Menu size={24} />
          </button>
          <h1 className="app-title">
            <div className="bot-avatar">
              <Scale size={18} color="white" />
            </div>
            Legal Advisor
          </h1>

          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            {backendStatus === "connected" ? (
              <>
                <CheckCircle size={16} color="#10b981" />
                <span
                  className="status-text"
                  style={{ fontSize: "14px", color: "#10b981" }}
                >
                  Connected
                </span>
              </>
            ) : backendStatus === "disconnected" ? (
              <>
                <AlertCircle size={16} color="#ef4444" />
                <span
                  className="status-text"
                  style={{ fontSize: "14px", color: "#ef4444" }}
                >
                  Offline
                </span>
              </>
            ) : (
              <>
                <Loader2 size={16} color="#f59e0b" className="spinner" />
                <span
                  className="status-text"
                  style={{ fontSize: "14px", color: "#f59e0b" }}
                >
                  Connecting...
                </span>
              </>
            )}
          </div>

        </header>

        {/* Chat Area */}
        <section className="chat-area">
          {messages.length === 0 && activeChat === "new" ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Scale size={40} color="white" />
              </div>
              <h2 className="welcome-title">How can I help you today?</h2>
              <p className="welcome-subtitle">
                Choose a legal source beside the chat box, then ask a property-law question.
              </p>
              <div className="suggested-questions" aria-label="Example questions">
                {suggestedQuestions[viewMode].map((question) => (
                  <button key={question} onClick={() => handleSendMessage(question)}>
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages-container">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message-row ${msg.type}`}>
                  {msg.type === "user" ? (
                    <div className="message-wrapper user">
                      <div className="message-bubble user">
                        <p className="message-text">{msg.content}</p>
                        <span className="message-time user">
                          {msg.timestamp}
                        </span>
                      </div>
                      <div className="user-avatar-msg">
                        <User size={20} color="#666" />
                      </div>
                    </div>
                  ) : (
                    /* Logic for Bot Response */
                    <div className="message-wrapper">
                      <div className="bot-avatar">
                        <Scale size={18} color="white" />
                      </div>

                      <div className={`bot-dual-container ${msg.viewMode || viewMode}`}>
                        {/* Pakistani Law Panel - Shows if mode is 'pakistan' or 'both' */}
                        {(msg.viewMode || viewMode) === "pakistani" && (
                          <div className="law-panel pakistan">
                            <div className="panel-header">
                              ⚖️ Pakistani Civil Law
                            </div>
                            <div className="message-bubble bot">
                              <StructuredText content={msg.pakistanContent || msg.content} />

                              {/* Sources specific to Pakistani context if they exist */}
                              {msg.sources &&
                                msg.sources.some(
                                  (s) => s.law_type === "Pakistani",
                                ) && (
                                  <div className="message-sources">
                                    <small>Legal Sources:</small>
                                    {msg.sources
                                      .filter((s) => s.law_type === "Pakistani")
                                      .map((source, sIdx) => (
                                        <div key={sIdx} className="source-item">
                                          • {source.content || source}
                                        </div>
                                      ))}
                                  </div>
                                )}
                              <span className="message-time bot">
                                {msg.timestamp}
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Islamic Law Panel - Shows if mode is 'islamic' or 'both' */}
                        {(msg.viewMode || viewMode) === "islamic" && (
                          <div className="law-panel islamic">
                            <div className="panel-header">
                              🌙 Islamic Sharia Law
                            </div>
                            <div className="message-bubble bot">
                              <StructuredText content={msg.islamicContent || msg.content} />

                              {/* Sources specific to Islamic context */}
                              {msg.sources &&
                                msg.sources.some(
                                  (s) => s.law_type === "Islamic",
                                ) && (
                                  <div className="message-sources">
                                    <small>Sharia References:</small>
                                    {msg.sources
                                      .filter((s) => s.law_type === "Islamic")
                                      .map((source, sIdx) => (
                                        <div key={sIdx} className="source-item">
                                          • {source.content || source}
                                        </div>
                                      ))}
                                  </div>
                                )}
                              <span className="message-time bot">
                                {msg.timestamp}
                              </span>
                            </div>
                          </div>
                        )}
                        {(msg.viewMode || viewMode) === "procedure" && (
                          <div className="law-panel procedure">
                            <div className="panel-header">Case Procedure</div>
                            <div className="message-bubble bot">
                              <StructuredText content={msg.procedureContent || msg.content} />
                              <span className="message-time bot">{msg.timestamp}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {/* NEW: Thinking Loader Bubble */}
              {isLoading && (
                <div className="message-row bot">
                  <div className="message-wrapper bot">
                    <div className="bot-avatar">
                      <Scale size={18} color="white" />
                    </div>
                    <div className="message-bubble bot thinking-bubble">
                      <div className="thinking-loader">
                        <span></span>
                        <span></span>
                        <span></span>
                      </div>
                      <p className="thinking-text">
                        Legal Advisor is thinking...
                      </p>
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
              <label className="mode-select-label">
                <span className="sr-only">Legal source</span>
                <select
                  className="mode-select"
                  value={viewMode}
                  onChange={(e) => setViewMode(e.target.value)}
                  disabled={isLoading}
                  aria-label="Choose legal source"
                >
                  <option value="pakistani">Pakistani</option>
                  <option value="islamic">Islamic</option>
                  <option value="procedure">Procedure</option>
                </select>
              </label>
              <input
                type="text"
                className="message-input"
                placeholder="Ask a legal question..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={handleKeyPress}
                disabled={isLoading || backendStatus !== "connected"}
              />
              <button
                className={`send-btn ${message.trim() && !isLoading && backendStatus === "connected" ? "active" : ""}`}
                onClick={handleSendMessage}
                disabled={
                  !message.trim() || isLoading || backendStatus !== "connected"
                }
              >
                {isLoading ? (
                  <Loader2 size={20} className="spinner" />
                ) : (
                  <Send size={20} />
                )}
              </button>
            </div>
          </div>
        </footer>
        {/* Inside <main className="main-content">, as the LAST element after </footer> */}
        <footer className="app-disclaimer-footer">
          Legal Advisor can make mistakes. It is using{" "}
          <a href="https://groq.com" target="_blank" className="groq-link">
            Groq LPU™
          </a>
        </footer>
      </main>
    </div>
  );
}
