import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './UserProfile.css';
import { deleteUser, getUserProfile, updateUser } from './api';

const UserProfile = () => {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editData, setEditData] = useState({ first: '',  email: '', password: '' });



  useEffect(() =>{
    const loadData = async () => {
       try{
        const data = await getUserProfile(userId);
        setUser(data);
        setEditData({first: data.first, email:data.email, password:''});
        if (data.queries?.length > 0) setSelectedSession(data.queries[0]);

       }catch (err) {
        console.error(err);
       }finally{
        setLoading(false);
       }
    };
    loadData();
   }, [userId]);

  // 2. Delete User with Token and Confirmation
  const handleDelete = async () => {
    const confirmDelete = window.confirm(
      "ARE YOU SURE? This will permanently delete this user, all their chat sessions, and all messages. This action cannot be undone."
    );

    if (confirmDelete) {
      try {
        await deleteUser(userId);
        alert("User deleted successfully.");
        navigate('/admin');
      } catch (error) {
        console.error("Delete Error: ", error);
        alert("An error occurred while deleting the user.");
      }
    }
  };

  // 3. Update User with Token
  const handleUpdate = async (e) => {
    e.preventDefault();
    try {
      const updatedUser = await updateUser(userId, editData);
      setUser({ ...user, ...updatedUser });
      setIsModalOpen(false);
      alert("User updated successfully!");
    } catch (err) { 
      console.error("Update error:", err);
      alert("Update failed due to server connection."); 
    }
  };

  if (loading) return <div className="loading">Loading Legal Profile...</div>;
  if (!user) return <div className="loading">User not found.</div>;

  return (
    <div className="profile-shell">
      {/* Sidebar and Chat Window remain identical to your current JSX */}
      <aside className="session-sidebar">
        <button className="back-btn" onClick={() => navigate('/admin')}>← Dashboard</button>
        <div className="user-mini-profile">
          <div className="profile-header-row">
            <h3>{user.first} {user.last}</h3>
            <button className="edit-gear" onClick={() => setIsModalOpen(true)}>⚙️</button>
          </div>
          <p>{user.email}</p>
        </div>
        <div className="session-list-label">Chat History</div>
        <div className="session-nav">
          {user.queries?.map(session => (
            <div 
              key={session.session_id} 
              className={`session-item ${selectedSession?.session_id === session.session_id ? 'active' : ''}`}
              onClick={() => setSelectedSession(session)}
            >
              <span className="icon">⚖️</span>
              <div className="session-info">
                <div className="session-title">{session.title}</div>
                <div className="session-date">{new Date(session.created_at).toLocaleDateString()}</div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-window">
        {selectedSession ? (
          <div className="message-container">
            {selectedSession.messages?.map(msg => (
              <div key={msg.message_id} className={`message-row ${msg.role}`}>
                <div className="message-bubble">
                  <div className="role-label">{msg.role === 'user' ? 'Client' : 'Legal Advisor'}</div>
                  <div className="content">{msg.content}</div>
                  <div className="msg-time">
                    {new Date(msg.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : <div className="no-selection">User doesn't have any Chat Session / Chat History</div>}
      </main>

      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3>Edit User Profile</h3>
              <button className='cross-btn' onClick={() => setIsModalOpen(false)}>×</button>
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
              <button type="button" className="del-btn" onClick={handleDelete}>Delete Account</button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default UserProfile;