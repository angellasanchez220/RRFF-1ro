// src/pages/Login.jsx
import { useState } from 'react';
import { login, getBaseApiUrl, setCustomApiUrl } from '../api';

export default function Login({ onLogin, isModal = false }) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [err,  setErr]  = useState('');
  const [loading, setLoading] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [serverUrl, setServerUrl] = useState(getBaseApiUrl());
  const [configSaved, setConfigSaved] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr('');
    setLoading(true);
    try {
      const data = await login(user, pass);
      // api.js ya guarda token/role/user/permisos en localStorage
      onLogin({ role: data.role, username: data.username, permisos: data.permisos || {} });
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = (e) => {
    e.preventDefault();
    setCustomApiUrl(serverUrl);
    setConfigSaved(true);
    setErr('');
    setTimeout(() => {
      setConfigSaved(false);
      setShowConfig(false);
    }, 1500);
  };

  const containerClass = isModal ? '' : 'login-page';

  return (
    <div className={containerClass}>
      <div className="login-card">
        <div className="login-logo">
          <div className="brand">RRFF<span className="accent"> SOFT</span></div>
        </div>
        <h2>S&amp;OP Planning Dashboard</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label>Usuario</label>
            <input
              type="text"
              value={user}
              onChange={e => setUser(e.target.value)}
              placeholder="Ej: Angella Sanchez o admin"
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="form-field">
            <label>Contraseña</label>
            <input
              type="password"
              value={pass}
              onChange={e => setPass(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
          {err && (
            <div className="error-msg" style={{ wordBreak: 'break-word', fontSize: '0.85rem', lineHeight: '1.4', margin: '10px 0' }}>
              {err}
            </div>
          )}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Iniciando sesión...' : 'Ingresar'}
          </button>
        </form>

        {/* Enlace para configurar la URL del backend si hay problemas de conexión */}
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <button
            type="button"
            onClick={() => setShowConfig(!showConfig)}
            style={{
              background: 'none', border: 'none', color: '#64748b', fontSize: '0.78rem',
              cursor: 'pointer', textDecoration: 'underline'
            }}>
            ⚙️ Configurar URL de Conexión (API)
          </button>
        </div>

        {showConfig && (
          <div style={{
            marginTop: 14, padding: 12, background: '#f8fafc', borderRadius: 8,
            border: '1px solid #cbd5e1', textAlign: 'left', fontSize: '0.8rem'
          }}>
            <label style={{ display: 'block', fontWeight: 600, color: '#334155', marginBottom: 4 }}>
              URL del Backend API:
            </label>
            <input
              type="text"
              value={serverUrl}
              onChange={e => setServerUrl(e.target.value)}
              placeholder="https://rrff-api.onrender.com/api"
              style={{
                width: '100%', padding: '6px 8px', borderRadius: 4,
                border: '1px solid #94a3b8', fontSize: '0.8rem', boxSizing: 'border-box'
              }}
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button
                type="button"
                onClick={handleSaveConfig}
                style={{
                  padding: '5px 12px', background: '#1d6b3e', color: '#fff', border: 'none',
                  borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem'
                }}>
                Guardar URL
              </button>
              <button
                type="button"
                onClick={() => {
                  setCustomApiUrl('');
                  setServerUrl(getBaseApiUrl());
                  setConfigSaved(true);
                  setTimeout(() => setConfigSaved(false), 1500);
                }}
                style={{
                  padding: '5px 10px', background: '#fff', color: '#64748b', border: '1px solid #cbd5e1',
                  borderRadius: 4, cursor: 'pointer', fontSize: '0.78rem'
                }}>
                Restablecer
              </button>
            </div>
            {configSaved && (
              <div style={{ color: '#16a34a', marginTop: 6, fontWeight: 600 }}>
                ✓ URL actualizada correctamente
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
