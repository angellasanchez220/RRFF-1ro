// src/App.jsx — Shell principal con routing manual
import { useState, useEffect } from 'react';
import './index.css';
import Login     from './pages/Login';
import Dashboard from './pages/Dashboard';
import Compras   from './pages/Compras';
import Admin     from './pages/Admin';
import Maquila   from './pages/Maquila';

export default function App() {
  const [auth, setAuth] = useState(null);  // { role, username, permisos }
  const [page, setPage] = useState('dashboard');

  // Restaurar sesión desde localStorage
  useEffect(() => {
    const token   = localStorage.getItem('rrff_token');
    const role    = localStorage.getItem('rrff_role');
    const username = localStorage.getItem('rrff_user');
    const permisos = JSON.parse(localStorage.getItem('rrff_permisos') || '{}');
    if (token && role) setAuth({ role, username, permisos });
  }, []);

  function handleLogin(data) {
    setAuth(data);
    setPage('dashboard');
  }

  function handleLogout() {
    localStorage.clear();
    setAuth(null);
  }

  if (!auth) return <Login onLogin={handleLogin} />;

  return (
    <div className="app-shell">
      {/* ── TOPBAR ── */}
      <header className="topbar">
        <div className="topbar-brand">
          <div className="dot" />
          RRFF <span style={{ color:'var(--lima)', marginLeft:4 }}>SOFT</span>
          <span style={{ color:'#555', fontWeight:400, marginLeft:8, fontSize:'0.75rem' }}>
            S&OP Planning
          </span>
        </div>

        <nav className="topbar-nav">
          <button
            className={page === 'dashboard' ? 'active' : ''}
            onClick={() => setPage('dashboard')}
          >
            📊 Dashboard
          </button>
          <button
            className={page === 'compras' ? 'active' : ''}
            onClick={() => setPage('compras')}
          >
            🛒 Compras
          </button>
          <button
            className={page === 'maquila' ? 'active' : ''}
            onClick={() => setPage('maquila')}
          >
            🏭 Maquila
          </button>
          {auth.role === 'admin' && (
            <button
              className={page === 'admin' ? 'active' : ''}
              onClick={() => setPage('admin')}
            >
              ⚙️ Admin
            </button>
          )}
        </nav>

        <div className="topbar-user">
          <span>{auth.username}</span>
          <span className="badge-role">{auth.role}</span>
          <button className="btn-logout" onClick={handleLogout}>Salir</button>
        </div>
      </header>

      {/* ── CONTENIDO ── */}
      {page === 'dashboard' && <Dashboard />}
      {page === 'compras'   && <Compras />}
      {page === 'maquila'   && <Maquila />}
      {page === 'admin'     && auth.role === 'admin' && <Admin />}
      {page === 'admin'     && auth.role !== 'admin' && (
        <div className="empty-state">
          <span style={{ fontSize:'2rem' }}>🔒</span>
          <span>Acceso restringido — solo administradores.</span>
        </div>
      )}
    </div>
  );
}
