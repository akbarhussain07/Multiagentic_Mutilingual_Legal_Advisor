import React, { useState } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock, Loader2 } from 'lucide-react'; // Added Loader2
import './Auth.css';

export default function Login() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  
  // 1. Add loading state
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true); // 2. Start loading

    try {
      const response = await fetch("http://127.0.0.1:8000/accounts/login/", { // Ensure this URL is correct
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
        localStorage.setItem('authToken', data.token);
        localStorage.setItem('chatUser', data.user.name);
        console.log("Login Successful");
        // Optional: Keep loading true here if you want it to spin until the redirect happens
        window.location.href = '/chatpage';
      } else {
        setError(data.error || "Login failed");
        setTimeout(() => setError(''), 3000);
        setLoading(false); // Stop loading on error
      }

    } catch (err) {
      console.log("Error:", err);
      setError("Server connection failed");
      setLoading(false); // Stop loading on catch
    }
    // Note: If you want to stop loading in all cases (except redirect), you can use a finally block,
    // but typically we leave it true on success so the user doesn't see the form reset before the page changes.
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
                <Loader2 size={18} className="animate-spin" /> {/* animate-spin usually needs CSS or Tailwind */}
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
