// import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import {BrowserRouter} from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import ReactDOM from 'react-dom/client';


import { GoogleOAuthProvider } from '@react-oauth/google';


import React from 'react';


// const root = ReactDOM.createRoot(document.getElementById('root'));
// root.render(<App />);

// ReactDOM.createRoot(document.getElementById('root')).render(
//   <GoogleOAuthProvider clientId="283760635076-l32hqgkdnrt08bgnj04cgqhsskruilq7.apps.googleusercontent.com">
//     <App />
//   </GoogleOAuthProvider>
// );

// createRoot(document.getElementById('root')).render(
//   <BrowserRouter>
//     <App />
//   </BrowserRouter>,
// )



const clientId = "18465317027-ttg662li8r46r3ns9pmuiqe26v89mi5q.apps.googleusercontent.com";

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <GoogleOAuthProvider clientId={clientId}>
      <App />
    </GoogleOAuthProvider>
  </BrowserRouter>
);