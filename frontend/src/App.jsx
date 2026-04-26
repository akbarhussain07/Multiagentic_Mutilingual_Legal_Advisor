import './App.css'
import Home from './Pages/Home'
import { Route, Routes } from 'react-router-dom'
import Login from './Pages/Login'
import Signup from './Pages/Signup'
import ForgotPassword from './Pages/ForgotPassword'
import ChatPage from './Pages/ChatPage'
import ResetPassword from './Pages/ResetPassword'
import AdminDashboard from './Pages/Admin'
import UserProfile from './Pages/UserProfile'
import ProtectedRoute from './Pages/ProtectedRoute'

function App() {

  const isAdmin = localStorage.getItem('isAdmin') === 'true';
  return (
    <div className='app'>
   
      <Routes>
        <Route path='/' element={<Home />} />
        <Route path='/login' element={<Login />}/>
        <Route path='/signup' element={<Signup />}/>
        <Route path='/forgot-password' element={<ForgotPassword />}/>
        <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
        <Route path='/chatpage' element={<ChatPage />}/>
        {/* <Route path='/admin' element={<AdminDashboard />}/> */}
        <Route path="/admin" element={
           <ProtectedRoute> 
             <AdminDashboard />
           </ProtectedRoute>
        } />
        <Route path="/admin/user/:userId" element={
           <ProtectedRoute> 
             <UserProfile />
           </ProtectedRoute>
        } />
      </Routes>
      
      
    </div>
  )
}

export default App
