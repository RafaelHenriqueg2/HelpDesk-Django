try {
  const theme = localStorage.getItem('helpdesk_theme');
  document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
} catch (_) { /* O portal continua funcionando sem armazenamento local. */ }
