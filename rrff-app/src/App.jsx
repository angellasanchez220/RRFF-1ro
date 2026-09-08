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

      {/* ── NOTIFICACIONES DE TAREAS EN SEGUNDO PLANO ── */}
      {auth && <TaskNotifications />}

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

function TaskNotifications() {
  const [tasks, setTasks] = useState({});
  const [closed, setClosed] = useState({});

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const { fetchTaskStatus } = await import('./api');
        const data = await fetchTaskStatus();
        setTasks(prevTasks => {
          let hasChanges = false;
          let shouldUnclose = [];
          
          Object.keys(data).forEach(key => {
            if (!prevTasks[key] || prevTasks[key].updated_at !== data[key].updated_at) {
              hasChanges = true;
              shouldUnclose.push(key);
            }
          });
          
          if (shouldUnclose.length > 0) {
            setClosed(prevClosed => {
              const nc = { ...prevClosed };
              shouldUnclose.forEach(k => delete nc[k]);
              return nc;
            });
          }
          
          return hasChanges ? data : prevTasks;
        });
      } catch (e) {
        // Ignorar errores de red
      }
    }, 5000);
    
    return () => clearInterval(interval);
  }, []);

  const activeTasks = Object.keys(tasks).filter(k => !closed[k]);
  if (activeTasks.length === 0) return null;

  return (
    <div style={{ position: 'fixed', top: 70, right: 20, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {activeTasks.map(k => {
        const t = tasks[k];
        let bg = '#e3f2fd', color = '#0d47a1', border = '#90caf9';
        if (t.status === 'done') { bg = '#e8f5e9'; color = '#1b5e20'; border = '#a5d6a7'; }
        if (t.status === 'error') { bg = '#ffebee'; color = '#b71c1c'; border = '#ef9a9a'; }

        return (
          <div key={k} style={{
            background: bg, color, border: `1px solid ${border}`,
            padding: '12px 16px', borderRadius: 8, boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            minWidth: 280, maxWidth: 350, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between'
          }}>
            <div>
              <strong style={{ display: 'block', marginBottom: 4, fontSize: '0.9rem' }}>
                {k === 'extract' ? 'Sincronización Matrix' : 'Reprocesamiento'}
              </strong>
              <span style={{ fontSize: '0.85rem' }}>{t.msg}</span>
            </div>
            <button
              onClick={() => setClosed(prev => ({ ...prev, [k]: true }))}
              style={{ background: 'none', border: 'none', color, cursor: 'pointer', fontSize: '1.2rem', lineHeight: 1, padding: '0 0 0 10px', marginTop: -2 }}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
