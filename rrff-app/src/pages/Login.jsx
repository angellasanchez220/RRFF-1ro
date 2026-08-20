// src/pages/Login.jsx
import { useState } from 'react';
import { login } from '../api';

export default function Login({ onLogin }) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [err,  setErr]  = useState('');
  const [loading, setLoading] = useState(false);

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

  return (
    <div className="login-page">
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
              placeholder="Ingresa tu usuario"
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
          {err && <div className="error-msg">{err}</div>}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Iniciando sesión...' : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  );
}
