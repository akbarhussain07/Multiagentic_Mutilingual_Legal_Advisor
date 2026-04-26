import React from 'react';
import { Navigate } from 'react-router-dom';

const ProtectedRoute = ({ children }) => {
  // Read directly from localStorage inside the component
  const isAdmin = localStorage.getItem('isAdmin') === 'true';

  if (!isAdmin) {
    console.log("Access Denied: Not an Admin");
    return <Navigate to="/login" replace />;
  }

  return children;
};

export default ProtectedRoute;