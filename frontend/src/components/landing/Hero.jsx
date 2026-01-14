import React from 'react';
import { ArrowRight, Zap,Gavel, PackageCheck,MessageSquare, Sparkles , Scale} from 'lucide-react';
import './Hero.css';

export const Hero = () => {
  return (
    <section className="section container">
      <div className="hero-grid">
        
        {/* Left Content */}
        <div className="hero-content">
         

          <h1 className="hero-title">
            Your Trusted Guide to  <br />
            <span className="text-gradient">Pakistani & Islamic Law</span>
          </h1>

          <p className="hero-description">
           
            Get instant guidance on legal matters with AI trained on Pakistani Law, 
            Islamic Sharia, and statutory laws. Available 24/7 in Urdu and English.
            <br />
           <PackageCheck size={16}/> Confidential  |  <Gavel size={16}/> Sharia-Compliant  |  <Scale size={16}/> Pakistani Law Expert


          </p>

          <div style={{ display: 'flex', gap: '1rem', marginBottom: '3rem' }}>
            <a href="#how-it-works"><button className="btn btn-primary">
              Try Demo <ArrowRight size={16} />
            </button>
            </a>
            <a href="/signup"> <button className="btn btn-outline"  >
              Register Now
            </button>
            </a>
          </div>

          <div className="hero-stats">
            <div className="stat-item">
              <div className="stat-item__value">
                <Zap size={20} color="#22d3ee" />
                <span>99%</span>
              </div>
              <p className="stat-item__label">Accuracy Rate</p>
            </div>
            <div className="stat-item">
              <div className="stat-item__value">
                <MessageSquare size={20} color="#a855f7" />
                <span>80%</span>
              </div>
              <p className="stat-item__label">Faster Response</p>
            </div>
          </div>
        </div>

        {/* Right Content - Chat UI Mockup */}
        <div style={{ position: 'relative' }}>
          <div className="chat-mockup">
            {/* Window Controls */}
            <div className="chat-mockup__header">
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <div style={{ width: '0.75rem', height: '0.75rem', borderRadius: '50%', backgroundColor: '#ef4444' }} />
                <div style={{ width: '0.75rem', height: '0.75rem', borderRadius: '50%', backgroundColor: '#eab308' }} />
                <div style={{ width: '0.75rem', height: '0.75rem', borderRadius: '50%', backgroundColor: '#22c55e' }} />
              </div>
              <div className="status-badge" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', backgroundColor: '#1e293b', padding: '0.2rem 0.6rem', borderRadius: '20px' }}>
                <div style={{ width: '0.4rem', height: '0.4rem', borderRadius: '50%', backgroundColor: '#22c55e' }} />
                <span style={{ fontSize: '0.7rem', color: '#94a3b8' }}>Live & Ready</span>
              </div>
            </div>

            {/* Chat Messages */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="bubble bubble--user">
                How do I file for Khula?
              </div>
              
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div className="navbar__logo-icon" style={{ width: '2rem', height: '2rem' }}>
                  <Scale size={14} color="white" />
                </div>
                <div className="bubble bubble--ai">
                  Under Pakistani law, you can file for Khula in Family Court. 
                  You may have to return the Haq Mehr you received.
                </div>
              </div>

              <div className="bubble bubble--user">
                That helps, thanks!
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#22d3ee', fontSize: '0.75rem' }}>
                <Sparkles size={12} />
                <span>AI is processing...</span>
              </div>
            </div>
          </div>

        
        </div>

      </div>
    </section>
  );
};