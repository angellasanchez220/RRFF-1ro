import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary capturó un error:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '40px 20px',
          maxWidth: '600px',
          margin: '50px auto',
          background: '#fff',
          borderRadius: '12px',
          border: '1px solid #ffd0d0',
          boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
          textAlign: 'center',
          fontFamily: 'system-ui, -apple-system, sans-serif'
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '15px' }}>⚠️</div>
          <h2 style={{ color: '#d32f2f', margin: '0 0 10px 0' }}>Ocurrió un error en esta pestaña</h2>
          <p style={{ color: '#555', fontSize: '0.95rem', lineHeight: '1.5' }}>
            Hubo un problema al renderizar el contenido de esta sección.
          </p>
          {this.state.error && (
            <pre style={{
              background: '#f8f9fa',
              color: '#c62828',
              padding: '12px',
              borderRadius: '6px',
              fontSize: '0.85rem',
              textAlign: 'left',
              overflowX: 'auto',
              border: '1px solid #eee',
              margin: '20px 0'
            }}>
              {this.state.error.toString()}
            </pre>
          )}
          <button
            onClick={this.handleReload}
            style={{
              background: '#0d47a1',
              color: '#fff',
              border: 'none',
              padding: '10px 24px',
              borderRadius: '6px',
              fontSize: '0.95rem',
              fontWeight: 'bold',
              cursor: 'pointer'
            }}
          >
            Recargar Página
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
