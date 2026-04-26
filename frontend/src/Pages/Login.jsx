import React, { useState } from 'react';
import { Eye, EyeOff, Scale, Mail, Lock, Loader2 } from 'lucide-react'; // Added Loader2
import './Auth.css';
import { GoogleOAuthProvider,GoogleLogin } from '@react-oauth/google';
import { useNavigate } from 'react-router-dom';

export default function Login() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true); // 2. Start loading

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
        localStorage.setItem('authToken', data.token);
        localStorage.setItem('chatUser', data.user.name);
        localStorage.setItem('id',data.user.id);
        console.log("Login Successful");
        if(data.user && data.user.is_superuser){
          localStorage.setItem('isAdmin','true');
          localStorage.setItem('user', JSON.stringify(data.user));
          
          console.log("Redirecting to Admin...");
          navigate('/admin');
        }else{
          localStorage.setItem('isAdmin', 'false');
          navigate('/chatpage');
        }
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
  };





  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true);
    try {
        const response = await fetch("http://127.0.0.1:8000/accounts/google-login/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_token: credentialResponse.credential }),
        });

        const data = await response.json();
        if (data.success) {
            localStorage.setItem('authToken', data.token);
            localStorage.setItem('chatUser', data.user.name);
            window.location.href = '/chatpage';
        } else {
            setError("Google Login Failed");
        }
    } catch (err) {
        setError("Server connection failed");
    } finally {
        setLoading(false);
    }
};




  return (
    <GoogleOAuthProvider clientId='283760635076-l32hqgkdnrt08bgnj04cgqhsskruilq7.apps.googleusercontent.com'>
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
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'center' }}>
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => setError("Google Auth Failed")}
            theme="outline"
            text="continue_with"
          />
        </div>
        <p className="switch-text">
          Don't have an account?{' '}
          <a href="/signup" className="switch-link">
            Sign Up
          </a>
        </p>
      </div>
    </div>
    </GoogleOAuthProvider>
  );
};
