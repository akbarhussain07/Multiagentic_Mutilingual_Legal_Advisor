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

// Delete Chat Session by sessionId
export const deleteChatSession = async (sessionId) => {
    const response = await fetch(`${API_BASE_URL}/history/${sessionId}/delete/`, {
        method: 'DELETE',
        headers: getHeaders()
    });
    
    if (!response.ok) throw new Error('Failed to delete session');
    return await response.json();
};


// ---- Admin Dashboard API's ------
// Fetch any user profile by userId
export const getUserProfile = async (userId) => {
    const response = await fetch(`http://127.0.0.1:8000/admin/users/${userId}/`, {
        method: 'GET',
        headers:getHeaders(),
    });
    if (!response.ok) throw new Error('Failed to fetch user profile');
    return response.json();
};

// Delete any user by it's userId
export const deleteUser = async (userId) => {
    const response = await fetch(`http://127.0.0.1:8000/admin/users/${userId}/delete/`,{
        method: 'DELETE',
        headers:getHeaders(),
    });
    if (!response.ok) throw new Error('Delete Failed');
    return true;
};

// Update any user by userId
export const updateUser = async (userId, editData) => {
    const response = await fetch(`http://127.0.0.1:8000/admin/users/${userId}/update/`, {
        method: 'PUT',
        headers:getHeaders(),
        body: JSON.stringify(editData),
    }); 
    if (!response.ok) throw new Error('Update failed on the server');
    return response.json();
};

// Fetch all users and shown in Admin Dashboard
export const getAllUsers = async () => {
    const response = await fetch('http://127.0.0.1:8000/admin/users/', {
        headers: getHeaders(),
    });
    if (!response.ok) throw new Error('User fetching failed on the server');
    return response.json();
};