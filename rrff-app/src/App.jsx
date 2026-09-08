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
  const [isSessionExpired, setIsSessionExpired] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  // Sync hash routing
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#/', '').replace('#', '') || 'dashboard';
      if (['dashboard', 'compras', 'maquila', 'admin'].includes(hash)) {
        setPage(hash);
      }
    };
    handleHashChange();
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    const currentHash = window.location.hash.replace('#/', '').replace('#', '');
    if (currentHash !== page) {
      window.location.hash = '/' + page;
    }
  }, [page]);

  // Manejo de expiración global
  useEffect(() => {
    const onExpired = () => setIsSessionExpired(true);
    window.addEventListener('session-expired', onExpired);
    return () => window.removeEventListener('session-expired', onExpired);
  }, []);

  // Restaurar sesión desde localStorage/sessionStorage
  useEffect(() => {
    const initSession = async () => {
      const token = localStorage.getItem('rrff_token');
      const role = localStorage.getItem('rrff_role');
      const username = localStorage.getItem('rrff_user');
      const permisos = JSON.parse(localStorage.getItem('rrff_permisos') || '{}');
      const hasSession = sessionStorage.getItem('femacoSessionAuthenticated');

      if (!token || !role) {
        setIsCheckingSession(false);
        return;
      }

      if (!hasSession) {
        setIsCheckingSession(false);
        return;
      }

      try {
        const { checkAuth } = await import('./api');
        await checkAuth();
        setAuth({ role, username, permisos });
      } catch (e) {
        // Aunque falle (ej. 401), montamos el shell con datos en caché para no perder la ruta.
        // Si fue 401, se disparó 'session-expired' y el modal bloqueará la pantalla inmediatamente.
        setAuth({ role, username, permisos });
      } finally {
        setIsCheckingSession(false);
      }
    };
    initSession();
  }, []);

  function handleLogin(data) {
    sessionStorage.setItem('femacoSessionAuthenticated', 'true');
    setAuth(data);
    setIsSessionExpired(false);
    if (!window.location.hash || window.location.hash === '#/') {
      setPage('dashboard');
    } else {
      const hash = window.location.hash.replace('#/', '').replace('#', '');
      if (['dashboard', 'compras', 'maquila', 'admin'].includes(hash)) {
        setPage(hash);
      } else {
        setPage('dashboard');
      }
    }
  }

  function handleLogout() {
    localStorage.clear();
    sessionStorage.removeItem('femacoSessionAuthenticated');
    setAuth(null);
  }

  if (isCheckingSession) return <div style={{padding: 40}}>Cargando sesión...</div>;
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

      {/* ── MODAL SESIÓN EXPIRADA ── */}
      {isSessionExpired && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 99999,
          display: 'flex', justifyContent: 'center', alignItems: 'center'
        }}>
          <div style={{
            background: '#1a1a1a', padding: 30, borderRadius: 12,
            border: '1px solid #333', maxWidth: 400, width: '100%',
            textAlign: 'center',
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
          }}>
            <h2 style={{color: '#ff5252', marginTop: 0}}>Sesión Expirada</h2>
            <p style={{color: '#ccc', marginBottom: 20}}>Tu sesión ha expirado por inactividad o seguridad. Vuelve a iniciar sesión para continuar sin perder tu trabajo actual.</p>
            <div style={{pointerEvents: 'auto'}}>
              <Login onLogin={handleLogin} isModal={true} />
            </div>
          </div>
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

      {/* ── MODAL SESIÓN EXPIRADA ── */}
      {isSessionExpired && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.8)', zIndex: 99999,
          display: 'flex', justifyContent: 'center', alignItems: 'center'
        }}>
          <div style={{
            background: '#1a1a1a', padding: 30, borderRadius: 12,
            border: '1px solid #333', maxWidth: 400, width: '100%',
            textAlign: 'center',
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
          }}>
            <h2 style={{color: '#ff5252', marginTop: 0}}>Sesión Expirada</h2>
            <p style={{color: '#ccc', marginBottom: 20}}>Tu sesión ha expirado. Vuelve a iniciar sesión para continuar.</p>
            <div style={{pointerEvents: 'auto'}}>
              <Login onLogin={handleLogin} isModal={true} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

