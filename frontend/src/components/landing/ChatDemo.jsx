import React, { useState, useEffect } from 'react';
import { Bot, User, Scale } from 'lucide-react';
import './ChatDemo.css';

const conversation = [
  { type: 'user', text: "How is inheritance distributed if a father passes away leaving a wife and two sons?", time: "10:23 AM" },
  { type: 'bot', text: "According to Islamic Inheritance Law (Sharia), the distribution would generally be:\n\n1. The Wife receives 1/8th of the estate (due to the presence of children).\n2. The remaining 7/8ths is distributed among the sons.\n\nWould you like me to cite the specific references from the Quran or Pakistani Succession laws?", time: "10:23 AM" },
  { type: 'user', text: "Yes, please referencing Pakistani law.", time: "10:24 AM" },
  { type: 'bot', text: "Under the Muslim Family Laws Ordinance, 1961, these shares are legally recognized. You would need to file for a 'Succession Certificate' in civil court to transfer assets. I can guide you through the documentation required for this certificate if you like.", time: "10:24 AM" },
  { type: 'user', text: "That would be helpful, thanks!", time: "10:25 AM" }
];

export const ChatDemo = () => {
  const [visibleMessages, setVisibleMessages] = useState(0);
  const [isTyping, setIsTyping] = useState(false);

  useEffect(() => {
    if (visibleMessages < conversation.length) {
      const timer = setTimeout(() => {
        setIsTyping(true);
        
        const typeTimer = setTimeout(() => {
          setIsTyping(false);
          setVisibleMessages(prev => prev + 1);
        }, 1500);

        return () => clearTimeout(typeTimer);
      }, 1500);

      return () => clearTimeout(timer);
    }
  }, [visibleMessages]);

  return (
    <section className="chat-section container" id='how-it-works'>
      <div className="chat-header-text">
        <h2>Natural Conversations, <span>Intelligent Solutions</span></h2>
        <p>See how our AI chatbot understands context and provides helpful, human-like responses.</p>
      </div>

      <div className="chat-window">
        {/* Header */}
        <div className="chat-top-bar">
          <div className="chat-status">
            <div className="bot-avatar">
              <Scale size={20} color="white" />
            </div>
            <div>
              <h3 style={{ fontWeight: 'bold', color: 'white', margin: 0, fontSize: '1rem' }}>Legal Advisor</h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                <span className="status-indicator" />
                <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Online</span>
              </div>
            </div>
          </div>
        </div>

        {/* Conversation Area */}
        <div className="chat-history">
          {conversation.slice(0, visibleMessages).map((msg, idx) => (
            <div 
              key={idx} 
              className={`message-row ${msg.type === 'user' ? 'message-row--user' : ''}`}
            >
              <div className={`avatar-small ${msg.type === 'user' ? 'avatar-small--user' : 'avatar-small--bot'}`}>
                {msg.type === 'user' ? <User size={16} color="white" /> : <Scale size={16} color="white" />}
              </div>
              
              <div className="message-bubble">
                <div className={`bubble-content ${msg.type === 'user' ? 'bubble-content--user' : 'bubble-content--bot'}`}>
                  {msg.text}
                </div>
                <div className={`message-time ${msg.type === 'user' ? 'text-right' : ''}`}>
                  {msg.time}
                </div>
              </div>
            </div>
          ))}

          {isTyping && (
            <div className="message-row">
              <div className="avatar-small avatar-small--bot">
                <Scale size={16} color="white" />
              </div>
              <div className="typing-dots">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          )}
        </div>

        {/* Input Footer */}
        <div className="chat-input-area">
          <input 
            type="text" 
            className="chat-input" 
            placeholder="Type your message..." 
            disabled 
          />
        </div>
      </div>
    </section>
  );
};