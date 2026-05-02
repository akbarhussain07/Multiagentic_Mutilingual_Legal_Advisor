import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock, Loader2 } from 'lucide-react'; // Added Loader2
import './Auth.css';
import { GoogleOAuthProvider,GoogleLogin } from '@react-oauth/google';
import { useNavigate } from 'react-router-dom';
import * as api from './api';


export default function Login() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();



  // Auto-clear errors after 3 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [error]);

const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // 1. Call the centralized API
      const data = await api.login({ email, password });

      // 2. Store user session data
      localStorage.setItem('authToken', data.token);
      localStorage.setItem('chatUser', data.user.name);
      localStorage.setItem('userEmail', data.user.email);
      localStorage.setItem('userId', data.user.id);

      
      // 3. Role-based Redirection
      if (data.user && data.user.is_superuser) {
        localStorage.setItem('isAdmin', 'true');
        localStorage.setItem('user', JSON.stringify(data.user));
        navigate('/admin');
      } else {
        localStorage.setItem('isAdmin', 'false');
        navigate('/chatpage');
      }

    } catch (err) {
      setError(err.message || "Server connection failed");
      setLoading(false);
    }
  };


  return (
    <div className="auth-container">
      <div className="auth-card login-card">
        <div className="auth-logo">
          <div className="logo-icon">
            <Scale size={20} color="#fff" />
          </div>
          <h1 className="logo-text">Legal Advisor</h1>
        </div>

        <h2 className="auth-title">Welcome Back</h2>
        <p className="auth-subtitle">Enter your credentials to access your account</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label className="form-label" htmlFor='email'>Email Address</label>
            <div className="input-wrapper">
              <Mail size={16} className="input-icon" />
              <input
                type="email"
                placeholder="you@example.com"
                className="form-input"
                id='email'
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading} /* Disable input while loading */
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <div className="input-wrapper">
              <Lock size={16} className="input-icon" />
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                className="form-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading} /* Disable input while loading */
              />
              <div
                className="eye-icon"
                onClick={() => !loading && setShowPassword(!showPassword)}
                style={{ cursor: loading ? 'not-allowed' : 'pointer' }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </div>
            </div>
          </div>
          
          {error && (
            <div className='error-message'> {error} </div>
          )}
          
          <a href="/forgot-password" className="forgot-link">
            Forgot Password?
          </a>

          {/* 3. Update Button with Loading State */}
          <button 
            type='submit' 
            className="auth-button" 
            disabled={loading}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
          >
            {loading ? (
              <>
                <Loader2 size={18} className="animate-spin" /> 
                <span>Signing In...</span>
              </>
            ) : (
              "Login"
            )}
          </button>
        </form>
        <p className="switch-text">
          Don't have an account?{' '}
          <a href="/signup" className="switch-link">
            Sign Up
          </a>
        </p>
      </div>
    </div>
  );
};
