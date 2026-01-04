// Backend API integration for Django server

const API_BASE_URL = 'http://localhost:8000/api';

// Check backend health status

export const checkHealth = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/health/`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error('Health check failed');
    }

    return await response.json();
  } catch (error) {
    console.error('Health check error:', error);
    throw error;
  }
};




// Helper to get headers with Auth Token
const getHeaders = () => {
    const token = localStorage.getItem('authToken');
    return {
        'Content-Type': 'application/json',
        'Authorization': `Token ${token}` 
    };
};

export const queryLegalQuestion = async (question, sessionId = null) => {
    const response = await fetch(`${API_BASE_URL}/query/`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ 
            question, 
            session_id: sessionId // Send null for new chat, ID for existing
        }),
    });
    if (!response.ok) throw new Error('Query failed');
    return await response.json();
};

// Fetch Sidebar Data
export const getUserSessions = async () => {
    const response = await fetch(`${API_BASE_URL}/history/`, {
        headers: getHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch history');
    return await response.json();
};

// Fetch Chat Messages
export const getSessionMessages = async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/history/${sessionId}/`, {
        headers: getHeaders()
    });
    if (!response.ok) throw new Error('Failed to fetch messages');
    return await response.json();
};


export const deleteChatSession = async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/history/${sessionId}/delete/`, {
        method: 'DELETE',
        headers: getHeaders()
    });
    
    if (!response.ok) throw new Error('Failed to delete session');
    return await response.json();
};