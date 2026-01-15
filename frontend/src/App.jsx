import './App.css'
import Home from './Pages/Home'
import { Route, Routes } from 'react-router-dom'
import Login from './Pages/Login'
import Signup from './Pages/Signup'
import ForgotPassword from './Pages/ForgotPassword'
import ChatPage from './Pages/ChatPage'
import ResetPassword from './Pages/ResetPassword'

function App() {

  return (
    <div className='app'>
   
      <Routes>
        <Route path='/' element={<Home />} />
        <Route path='/login' element={<Login />}/>
        <Route path='/signup' element={<Signup />}/>
        <Route path='/forgot-password' element={<ForgotPassword />}/>
        <Route path="/reset-password/:uid/:token" element={<ResetPassword />} />
        <Route path='/chatpage' element={<ChatPage />}/>
      </Routes>
      
    </div>
  )
}

export default App
