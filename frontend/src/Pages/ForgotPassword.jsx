import React, { useState } from 'react';
import { Scale, Mail, ArrowLeft, AlertCircle } from 'lucide-react';
import './Auth.css';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [emailSent, setEmailSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');


  try {
    const response = await fetch('http://localhost:8000/accounts/password-reset/', { // Matches new URL
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
    });

    const data = await response.json();

    if (response.ok) {
      setEmailSent(true);
    } else {
    // If backend sends { "error": "This email account does not exist" }
    // We set that as the error message to display in the red box
      setError(data.error || "Failed to connect to the server.");
    }
  } catch (err) {
      setError("Failed to connect to the server.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card forgot-card">
        <div className="auth-logo">
          <div className="logo-icon">
            <Scale size={20} color="#fff" />
          </div>
          <h1 className="logo-text">Legal Advisor</h1>
        </div>

        <a href="/login" className="back-button">
          <ArrowLeft size={14} /> Back to Login
        </a>

        <h2 className="auth-title">Reset Password</h2>
        <p className="auth-subtitle">Enter your email and we'll send you a reset link</p>

        {emailSent ? (
          <div className="success-message">
             <div className="success-title">Check Your Email</div>
             <p className="success-text">We've sent a password reset link to <strong>{email}</strong>.</p>
          </div>
        ) : (
          <div className="auth-form">
            <div className="form-group">
              <label className="form-label">Email Address</label>
              <div className="input-wrapper">
                <Mail size={16} className="input-icon" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="form-input"
                  required
                />
              </div>
            </div>

            {error && (
              <div className="error-message" style={{color: 'red', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '5px'}}>
                 <AlertCircle size={16}/> {error}
              </div>
            )}

            <button onClick={handleSubmit} className="auth-button" disabled={loading}>
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default ForgotPassword;