import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './Admin.css';
import { getAllUsers, updateUser, uploadDocument, getUploadStatus } from './api';


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
  
  const [activeTasks, setActiveTasks] = useState([]); // List of background tasks
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadLawType, setUploadLawType] = useState('Pakistani');
 
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

useEffect(() => {
    const pollInterval = setInterval(async () => {
        if (activeTasks.length === 0) return;

        const updatedTasks = await Promise.all(
            activeTasks.map(async (task) => {
                if (task.status === 'completed' || task.status === 'failed') return task;

                try {
                    const statusData = await getUploadStatus(task.id);
                    if (statusData) {
                        return { 
                            ...task, 
                            progress: statusData.progress, 
                            status: statusData.status,
                            current: statusData.current,
                            total: statusData.total 
                        };
                    }
                } catch (err) {
                    console.error("Polling error:", err);
                }
                return task;
            })
        );
        setActiveTasks(updatedTasks);
    }, 3000);

    return () => clearInterval(pollInterval);
}, [activeTasks]);

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
          <button className={`nav-item ${activeTab === 'upload' ? 'active' : ''}`} onClick={() => { setActiveTab('upload'); setSidebarOpen(false); }}>Upload Documents</button>
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
        {activeTab === 'upload' && (
  <div className="panel" style={{ padding: '30px', color:'black'}}>
    <h3>Upload Legal Documents to Vector DB</h3>
    <p>
      Upload Markdown or PDF legal sources to index them in Qdrant.
    </p>
    
    <div className="upload-section" style={{ marginTop: '20px' }}>
      <div className="input-group">
        <label>Law Category</label>
        <select 
          value={uploadLawType} 
          onChange={(e) => setUploadLawType(e.target.value)}
          style={{ padding: '8px', borderRadius: '4px', marginBottom: '15px' }}
        >
          <option value="Pakistani">Pakistani Law</option>
          <option value="Islamic">Islamic Law</option>
          <option value="Procedure">Pakistani procedure / case law</option>
        </select>
      </div>

      <input 
        type="file" 
        accept=".md,.markdown,.pdf"
        onChange={(e) => setSelectedFile(e.target.files[0])} 
      />
      
<button 
  className="save-btn" 
  style={{ marginTop: '20px', width: '200px' }}
  disabled={!selectedFile || uploading}
  onClick={async () => {
    setUploading(true);
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('law_type', uploadLawType);

    try {
      console.log("Sending file to server...");
      const result = await uploadDocument(formData); 
      
      // FIX: Add the task to state so the useEffect starts polling
      const newTask = {
        id: result.task_id,
        fileName: selectedFile.name,
        progress: 0,
        status: 'starting'
      };
      setActiveTasks(prevTasks => [...prevTasks, newTask]);

      alert(`Upload successful! Task ID: ${result.task_id}. Indexing has started in the background.`);
      
      setSelectedFile(null); 
      document.querySelector('input[type="file"]').value = ""; 

    } catch (err) {
      console.error("Upload error:", err);
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
    }
  }}
>
  {uploading ? "Uploading..." : "Start Indexing"}
</button>

{/* NEW: Visual Progress Display (Place this right below the button) */}
<div style={{ marginTop: '20px' }}>
  {activeTasks.map(task => (
    <div key={task.id} style={{ marginBottom: '15px', padding: '10px', border: '1px solid #ccc', borderRadius: '5px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '5px' }}>
        <span>{task.fileName}</span>
        <span style={{ color: task.status === 'completed' ? 'green' : 'orange' }}>{task.status}</span>
      </div>
      <div style={{ width: '100%', height: '8px', background: '#eee', borderRadius: '4px' }}>
        <div style={{ width: `${task.progress}%`, height: '100%', background: '#2d6a4f', borderRadius: '4px', transition: 'width 0.4s' }}></div>
      </div>
      <div style={{ fontSize: '10px', marginTop: '5px' }}>
        {task.progress}% - {task.total ? `Page ${task.current} of ${task.total}` : 'Initializing...'}
      </div>
    </div>
  ))}
</div>
    </div>
  </div>
)}
{activeTab === 'dashboard' && (
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
)}
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
