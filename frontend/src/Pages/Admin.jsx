import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './Admin.css';
import { getAllUsers, updateUser } from './api';


const COLORS = ['#2d6a4f', '#5b8dd9', '#b85c38', '#8b5e99', '#c07d2e', '#3a7a78', '#c0543a', '#4a7c59'];

const AdminDashboard = () => {
  const { userId } = useParams();
  const [user, setUser] = useState(null);
  const [users, setUsers] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const [showAdminDropdown, setShowAdminDropdown] = useState(false);
  const [isAdminModalOpen, setIsAdminModalOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  const adminData = JSON.parse(localStorage.getItem('user') || '{}');

  const [editData, setEditData] = useState({ 
    first: adminData.name || '',
    email: adminData.email || '',
    password: ''
  });


  const handleLogout = () => {
    localStorage.clear(); // Clears token and admin status
    navigate('/login');
  };


  useEffect(() => {
   const fetchUsers = async () => {
    // const token = localStorage.getItem('authToken');

    try {
      const data = await getAllUsers();
      setUsers(data);
      setAllUsers(data);
      setLoading(false);
    } catch(error) {
      console.error("Connection Error:", error);
      setLoading(false);
    }
  };
  fetchUsers();
}, []);

  const totalUsersCount = allUsers.length;
 const totalQueriesCount = Array.isArray(allUsers) 
  ? allUsers.reduce((sum, user) => sum + (user.queries?.length || 0), 0)
  : 0;

//  Calculate Average Rating
const calculateAvgRating = () => {
  if (!allUsers || allUsers.length === 0) return "0.0";
  
  // Filter only users who have actually given a rating (> 0)
  const ratedUsers = allUsers.filter(u => u.rating && u.rating > 0);
  
  if (ratedUsers.length === 0) return "0.0";
  
  const sum = ratedUsers.reduce((acc, u) => acc + u.rating, 0);
  const avg = sum / ratedUsers.length;
  
  return avg.toFixed(1); // Returns string like "4.2"
};
  const averageRating = calculateAvgRating();

//Calculate Active Users (Last 60 minutes)
const calculateActiveUsers = () => {
  if (!allUsers || allUsers.length === 0) return 0;

  const fifteenMinutesAgo = new Date(Date.now() - 60 * 60 * 1000);

  const activeCount = allUsers.filter(u => {
    // Check if any of the user's queries/sessions were updated recently
    return u.queries?.some(session => {
      const sessionDate = new Date(session.updated_at);
      return sessionDate > fifteenMinutesAgo;
    });
  }).length;

  return activeCount;
};

const activeUsersCount = calculateActiveUsers();
  
  const handleSearch = (e) => {
    const term = e.target.value.toLowerCase();
    setSearchTerm(term);
    const filtered = allUsers.filter(u => 
      u.first.toLowerCase().includes(term) || u.email.toLowerCase().includes(term)
    );
    setUsers(filtered);
  };

  const getInitials = (u) => {
    return ((u.first || '')[0] || '') + (u.last ? u.last[0] : u.username[1] || '').toUpperCase();
  };
   

  const handleUpdate = async (e) => {
     e.preventDefault();
     const currentAdminId = adminData.id;
     if (!currentAdminId){
      alert("Admin ID not found. Please re-login.");
      return;
     }
     try{
      const updatedAdmin = await updateUser(currentAdminId, editData );
      const newAdminData = {
        ...adminData,
        name: updatedAdmin.first,
        email: updatedAdmin.email
      };
      localStorage.setItem('user', JSON.stringify(newAdminData));

      setIsAdminModalOpen(false);
      alert("Your Profile updated successfully!");
      window.location.reload();
     } catch (err) {
      console.error("Update error:", err);
      alert("Update failed due to server connection");
     }
  };
  return (
    <div className="shell">   
      <header className="topbar">
        <button className="topbar-menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <div className="topbar-logo"><span className="dot"></span>LegalAdvisor · Admin</div>
        
        <div className="topbar-right">
          <span className="chip">X-RAG System v1.0</span>
          
          {/* Admin Avatar with Dropdown Trigger */}
          <div className="avatar-wrapper">
            <div className="avatar admin-avatar" onClick={() => setShowAdminDropdown(!showAdminDropdown)}>
              {adminData.name ? adminData.name.slice(0,2).toUpperCase(): 'AF'}
            </div>
            
            {showAdminDropdown && (
              <div className="admin-dropdown">
                <div className="dropdown-info">
                  <strong>{adminData.name || 'Admin'}</strong>
                  <span>{adminData.email}</span>
                </div>
                <hr />
                <button onClick={() => {
                  setEditData({ first:adminData.name, email: adminData.email, password: ''}); 
                  setIsAdminModalOpen(true); 
                  setShowAdminDropdown(false); 
                  }}>
                  👤 My Profile
                </button>
                <button className="logout-item" onClick={handleLogout}>
                  🚪 Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {isAdminModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content">
             <div className="modal-header">
                <h3>Admin Settings</h3>
                <button className='cross-btn' onClick={() => setIsAdminModalOpen(false)}>×</button>
             </div>
             
                <form onSubmit={handleUpdate}>
              <div className="input-group">
                <label>User Name</label>
                <input type="text" value={editData.first} onChange={e => setEditData({...editData, first: e.target.value})} />
              </div>
              <div className="input-group">
                <label>Email</label>
                <input type="email" value={editData.email} onChange={e => setEditData({...editData, email: e.target.value})} />
              </div>
              <div className="input-group password-group">
                <label>Reset Password</label>
                <input type="password" placeholder="New password (optional)" onChange={e => setEditData({...editData, password: e.target.value})} />
              </div>
              <button type="submit" className="save-btn">Update Account</button>
            </form>
           
          </div>
        </div>
      )}

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="admin-sidebar-overlay visible" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <nav className={`sidebar-main ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-section">
          <div className="sidebar-label">Overview</div>
          <button className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => { setActiveTab('dashboard'); setSidebarOpen(false); }}>Dashboard</button>
          <button className={`nav-item ${activeTab === 'users' ? 'active' : ''}`} onClick={() => { setActiveTab('users'); setSidebarOpen(false); }}>Users</button>
        </div>
        
        <div style={{ marginTop: 'auto', padding: '20px', textAlign: 'center', fontSize: '11px', color: 'var(--txt-tertiary)' }}>
          <strong>Akhuwat College Kasur</strong><br />
          Final Year Project 22-26
        </div>
      </nav>

      {/* Main Content */}
      <main className="main">
        <div className="stats-row">
          <StatCard label="Total Users" value={allUsers.length} color="#2d6a4f" sub="↑ 2 this week" />
          <StatCard label="Total Queries" value={totalQueriesCount} color="#e8c97e" sub="↑ 12 today" />
          <StatCard label="Avg Rating" value={averageRating} color="#5b8dd9" sub="★ out of 5" />
          <StatCard label="Active Today" value={activeUsersCount} color="#c0543a" sub="↓ 1 vs yesterday" />
        </div>

        <div className="content-grid">
          {/* User List Panel */}
          <div className="panel">
            <div style={{ padding: '15px', borderBottom: '1px solid var(--bdr)' , margin:'10px'}}>
              <input 
                className="nav-item" 
                style={{ border: '1px solid var(--bdr)', padding: '8px' }}
                placeholder="Search users..." 
                value={searchTerm}
                onChange={handleSearch}
              />
            </div>
            <div className="user-list">
              {loading ? (
                <div style={{ padding: '20px', textAlign:'center'}}>Loading users...</div>
              ):(
              users.map((user) => (
                <div 
                  key={user.id} 
                  className="user-row"
                  onClick={() => navigate(`/admin/user/${user.id}`)}
                >
                  <div className="avatar" style={{ background: `${COLORS[user.id % COLORS.length]}22`, color: COLORS[user.id % COLORS.length] }}>
                    {getInitials(user)}
                  </div>
                  <div style={{ flex: 1, color: COLORS[user.id % COLORS.length] }}>
                    <div style={{ fontSize: '13px', fontWeight: '500' }}>{user.first} {user.last}</div>
                    <div style={{ fontSize: '11px', color: 'var(--txt-tertiary)' }}>{user.email}</div>
                  </div>
                  <div style={{ textAlign: 'right', fontSize: '11px', color: COLORS[user.id % COLORS.length] }}>
                    <div>{user.queries?.length || 0} queries</div>
                  </div>
                </div>
              ))
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};

const StatCard = ({ label, value, color, sub }) => (
  <div className="stat-card" style={{ '--stripe-color': color }}>
    <div style={{ fontSize: '11px', color: 'var(--txt-tertiary)', textTransform: 'uppercase' }}>{label}</div>
    <div className="stat-num" >{value}</div>
    <div style={{ fontSize: '11px', color: '#2d6a4f' }}>{sub}</div>
  </div>
);

export default AdminDashboard;