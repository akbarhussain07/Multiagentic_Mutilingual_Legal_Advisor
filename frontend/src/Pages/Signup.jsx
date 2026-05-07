import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock, User, CheckCircle, Loader2 } from 'lucide-react';
import './Auth.css';
import * as api from './api';

export default function Signup() {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [error, setError] = useState('');

  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmpass: ''
  });

  const [strength, setStrength] = useState({
    length: false,
    number: false,
    upper: false,
    special: false,
  });

  // 1. Password Strength Logic
  useEffect(() => {
    const pwd = formData.password;
    setStrength({
      length: pwd.length >= 8,
      number: /[0-9]/.test(pwd),
      upper: /[A-Z]/.test(pwd),
      special: /[!@#$%^&*(),.?":{}|<>]/.test(pwd),
    });
  }, [formData.password]);

  // 2. Automatic error clearing
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  const strengthScore = Object.values(strength).filter(Boolean).length;

  const getStrengthMetadata = () => {
    if (formData.password.length === 0) return { width: '0%', color: 'transparent', label: '' };
    switch (strengthScore) {
      case 1: return { width: '25%', color: '#ef4444', label: 'Weak' };
      case 2: return { width: '50%', color: '#f59e0b', label: 'Fair' };
      case 3: return { width: '75%', color: '#3b82f6', label: 'Good' };
      case 4: return { width: '100%', color: '#10b981', label: 'Strong' };
      default: return { width: '0%', color: 'transparent', label: '' };
    }
  };

  const metadata = getStrengthMetadata();
  
  // 3. New Match Logic
  const passwordsMatch = formData.confirmpass.length > 0 && formData.password === formData.confirmpass;
  
  // 4. Update Requirement: Allow Good (3) or Strong (4)
  const isPasswordAcceptable = strengthScore >= 3;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!isPasswordAcceptable) {
      setError("Please reach at least 'Good' strength");
      return;
    }

    if (!passwordsMatch) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);
    try {
      await api.signup({
        username: formData.username,
        email: formData.email,
        password: formData.password,
      });
      setShowSuccess(true);
      setTimeout(() => { window.location.href = "/login"; }, 3000);
    } catch (err) {
      setError(err.message || "Server connection failed");
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      {showSuccess && (
        <div className="popup-overlay">
          <div className="popup-card">
            <CheckCircle size={50} color="#10B981" style={{ marginBottom: '15px' }} />
            <h3 className="popup-title">Account Created!</h3>
            <p className="popup-message">Registered successfully. Redirecting to login...</p>
            <div className="popup-spinner"><Loader2 size={24} className="animate-spin" color="#0ea5e9" /></div>
          </div>
        </div>
      )}

      <div className="auth-card signup-card">
        <div className="auth-logo">
          <div className="logo-icon"><Scale size={20} color="#fff" /></div>
          <h1 className="logo-text">Legal Advisor</h1>
        </div>

        <h2 className="auth-title">Create Account</h2>
        <form onSubmit={handleSubmit} className="auth-form">
          {/* Username & Email */}
          <div className="form-group">
            <label className="form-label" htmlFor='username'>User Name</label>
            <div className="input-wrapper">
              <User size={16} className="input-icon" />
              <input type="text" id='username' className="form-input" placeholder='XYZ' value={formData.username} onChange={(e) => setFormData({ ...formData, username: e.target.value })} required disabled={loading} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor='email'>Email Address</label>
            <div className="input-wrapper">
              <Mail size={16} className="input-icon" />
              <input type="email" id='email' className="form-input" placeholder='xyz@example.com' value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} required disabled={loading} />
            </div>
          </div>

          {/* Password Section */}
          <div className="form-group">
            <label className="form-label" htmlFor='password'>Password</label>
            <div className="input-wrapper">
              <Lock size={16} className="input-icon" />
              <input type={showPassword ? "text" : "password"} id='password' className="form-input" placeholder="Use 8+ chars (A-z, 0-9, !@#)" value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} required disabled={loading} />
              <div className="eye-icon" onClick={() => setShowPassword(!showPassword)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</div>
            </div>
            {formData.password.length > 0 && (
              <div className="strength-meter-container">
                <div className="strength-meter-bar">
                  <div className="strength-meter-fill" style={{ width: metadata.width, backgroundColor: metadata.color }}></div>
                </div>
                <span className="strength-label" style={{ color: metadata.color }}>{metadata.label}</span>
              </div>
            )}
          </div>

          {/* Confirm Password Section with Match Bar */}
          <div className="form-group">
            <label className="form-label" htmlFor='confirm-pass'>Confirm Password</label>
            <div className="input-wrapper">
              <Lock size={16} className="input-icon" />
              <input type={showConfirmPassword ? "text" : "password"} id='confirm-pass' className="form-input" placeholder="Confirm your password" value={formData.confirmpass} onChange={(e) => setFormData({ ...formData, confirmpass: e.target.value })} required disabled={loading} />
              <div className="eye-icon" onClick={() => setShowConfirmPassword(!showConfirmPassword)}>{showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}</div>
            </div>
            
            {/* MATCH BAR RUNTIME */}
            {formData.confirmpass.length > 0 && (
              <div className="strength-meter-container">
                <div className="strength-meter-bar">
                  <div 
                    className="strength-meter-fill" 
                    style={{ 
                      width: passwordsMatch ? '100%' : '50%', 
                      backgroundColor: passwordsMatch ? '#10b981' : '#ef4444' 
                    }}
                  ></div>
                </div>
                <span className="strength-label" style={{ color: passwordsMatch ? '#10b981' : '#ef4444' }}>
                  {passwordsMatch ? 'Matched' : 'No Match'}
                </span>
              </div>
            )}
          </div>

          {error && <div className='error-message'>{error}</div>}

          <button 
            type='submit' 
            className="auth-button" 
            disabled={loading || !isPasswordAcceptable || !passwordsMatch}
          >
            {loading ? "Creating Account..." : "Create Account"}
          </button>
        </form>

        <p className="switch-text">Already have an account? <a href="/login" className="switch-link">Login</a></p>
      </div>
    </div>
  );
}