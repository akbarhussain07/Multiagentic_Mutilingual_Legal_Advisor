// api.js - Backend API integration for Django server

const API_BASE_URL = 'http://localhost:8000/api';

/**
 * Check backend health status
 */
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

/**
 * Query legal question to the backend
 */
export const queryLegalQuestion = async (question) => {
  try {
    const response = await fetch(`${API_BASE_URL}/query/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      throw new Error('Query failed');
    }

    return await response.json();
  } catch (error) {
    console.error('Query error:', error);
    throw error;
  }
};