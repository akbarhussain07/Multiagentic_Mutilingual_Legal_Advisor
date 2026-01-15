import React, { useState } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock, User, CheckCircle, Loader2 } from 'lucide-react';
import './Auth.css';

export default function Signup() {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  // 1. Add Loading and Success states
  const [loading, setLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const [formData, setFormData] = useState({
    username:'',
    email:'',
    password:'',
    confirmpass:''
  });
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    // Validate passwords match
    if (formData.password !== formData.confirmpass) {
      setError("Passwords do not match");
      setTimeout(() => setError(''), 3000);
      return;
    }

    setLoading(true); // Start loading

    try {
      const response = await fetch("http://127.0.0.1:8000/accounts/signup/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: formData.username,
          email: formData.email,
          password: formData.password,
        }),
      });

      const data = await response.json();

      if (response.ok || data.success) {
        // 2. On Success: Show Popup and wait 3 seconds before redirect
        setShowSuccess(true);
        setTimeout(() => {
           window.location.href = "/login";
        }, 3000);
      } else {
        // Handle API errors
        setError(data.error || "Signup failed");
        setTimeout(() => setError(''), 3000);
        setLoading(false);
      }
    } catch (err) {
      console.log("Error:", err);
      setError("Server connection failed");
      setTimeout(() => setError(''), 3000);
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      
      {/* 3. The Success Popup Overlay */}
      {showSuccess && (
        <div className="popup-overlay">
          <div className="popup-card">
            <CheckCircle size={50} color="#10B981" style={{ marginBottom: '15px' }} />
            <h3 className="popup-title">Account Created!</h3>
            <p className="popup-message">
              Your account has been registered successfully. <br/>
              Redirecting to login...
            </p>
            <div className="popup-spinner">
               <Loader2 size={24} className="animate-spin" color="#0ea5e9"/>
            </div>
          </div>
        </div>
      )}

      <div className="auth-card signup-card">
        <div className="auth-logo">
          <div className="logo-icon">
            <Scale size={20} color="#fff" />
          </div>
          <h1 className="logo-text">Legal Advisor</h1>
        </div>

        <h2 className="auth-title">Create Account</h2>
        <p className="auth-subtitle">Join us to get instant legal guidance</p>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label className="form-label" htmlFor='username'>User Name</label>
            <div className="input-wrapper">
              <User size={16} className="input-icon" />
              <input
                type="text"
                placeholder="XYZ"
                className="form-input"
                id='username'
                value={formData.username}
                onChange={(e) =>setFormData({...formData, username: e.target.value})}
                required
                disabled={loading || showSuccess}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor='email'>Email Address</label>
            <div className="input-wrapper">
              <Mail size={16} className="input-icon" />
              <input
                type="email"
                placeholder="xyz@example.com"
                className="form-input"
                id='email'
                value={formData.email}
                onChange={(e) => setFormData({...formData, email:e.target.value})}
                required
                disabled={loading || showSuccess}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor='password'>Password</label>
            <div className="input-wrapper">
              <Lock size={16} className="input-icon" />
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Create a strong password"
                className="form-input"
                id='password'
                value={formData.password}
                onChange={(e)=>setFormData({...formData, password:e.target.value})}
                required
                disabled={loading || showSuccess}
              />
              <div 
                className="eye-icon"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </div>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor='confirm-pass'>Confirm Password</label>
            <div className="input-wrapper">
              <Lock size={16} className="input-icon" />
              <input
                type={showConfirmPassword ? "text" : "password"}
                placeholder="Confirm your password"
                className="form-input"
                id='confirm-pass'
                value={formData.confirmpass}
                onChange={(e)=>setFormData({...formData, confirmpass:e.target.value})}
                required
                disabled={loading || showSuccess}
              />
              <div 
                className="eye-icon"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              >
                {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </div>
            </div>
          </div>

          {error &&(
            <div className='error-message'>{error}</div>
          )}

          <button type='submit' className="auth-button" disabled={loading || showSuccess}>
            {loading ? "Creating Account..." : "Create Account"}
          </button>
        </form>

        <p className="switch-text">
          Already have an account?{' '}
          <a href="/login" className="switch-link">
            Login
          </a>
        </p>
      </div>
    </div>
  );
};