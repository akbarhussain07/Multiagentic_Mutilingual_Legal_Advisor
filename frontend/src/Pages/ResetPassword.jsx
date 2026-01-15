import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom'; // Assuming react-router-dom
import { Scale, Lock, CheckCircle, ArrowLeft, Eye, EyeOff } from 'lucide-react';
import './Auth.css';

const ResetPassword = () => {
  const { uid, token } = useParams();
  const navigate = useNavigate();
  
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (password !== confirmPassword) {
        setError("Passwords do not match");
        setTimeout(() => setError(''), 3000);
        setLoading(false);
        return;
    }

    try {
      const response = await fetch('http://localhost:8000/accounts/password-reset-confirm/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            uidb64: uid, 
            token: token, 
            password: password,
            confirm_password: confirmPassword
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(true);
        setTimeout(() => navigate('/login'), 3000); // Redirect after 3s
      } else {
        // Display backend errors (e.g. Invalid Token, Password too short)
        setError(JSON.stringify(data));
        setTimeout(() => setError(''), 3000);
      }
    } catch (err) {
      setError("Failed to connect to server.");
      setTimeout(() => setError(''), 3000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="logo-icon"><Scale size={20} color="#fff" /></div>
          <h1 className="logo-text">Legal Advisor</h1>
        </div>
         <a href="/login" className="back-button">
          <ArrowLeft size={14} /> Back to Login
        </a>

        <h2 className="auth-title">Set New Password</h2>

        {success ? (
          <div className="success-message">
            <CheckCircle size={40} color="green" style={{margin: '0 auto 10px'}}/>
            <div className="success-title">Success!</div>
            <p className="success-text">Your password has been reset. Redirecting to login...</p>
          </div>
        ) : (
          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">New Password</label>
              <div className="input-wrapper">
                <Lock size={16} className="input-icon" />
                <input
                  type={showPassword ? "text": "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="form-input"
                  required
                  minLength={8}
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
              <label className="form-label">Confirm Password</label>
              <div className="input-wrapper">
                <Lock size={16} className="input-icon" />
                <input
                  type={showPassword ? "text": "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="form-input"
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

            {error && <div className="error-message" style={{color:'red', marginBottom:'10px'}}>{error}</div>}

            <button type="submit" className="auth-button" disabled={loading}>
              {loading ? 'Reseting...' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};

export default ResetPassword;