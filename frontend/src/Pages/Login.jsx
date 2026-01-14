import React, { useState } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock } from 'lucide-react';
import './Auth.css';

export default function Login(){
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');


const handleSubmit = async (e) => {
    e.preventDefault();
    setError(''); // Clear previous errors

    try {
      const response = await fetch("http://127.0.0.1:8000/accounts/login/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: email,
          password: password,
        }),
      });

      const data = await response.json();

      if (data.success) {
        // SUCCESS: REDIRECT HERE 
        // 1. SAVE THE NAME TO STORAGE
        localStorage.setItem('authToken', data.token);
        localStorage.setItem('chatUser', data.user.name); 
        console.log("Login Successful");
        window.location.href = '/chatpage'; 
      } else {
        setError(data.error || "Login failed");
        setTimeout(() => setError(''), 3000);
      }

    } catch (err) {
      console.log("Error:", err);
      setError("Server connection failed");
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
                onChange={(e)=>setEmail(e.target.value)}
                required
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
                onChange={(e)=>setPassword(e.target.value)}
                required
              />
              <div 
                className="eye-icon"
                onClick={() => setShowPassword(!showPassword)}
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

          <button type='submit' className="auth-button">
            Login
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
