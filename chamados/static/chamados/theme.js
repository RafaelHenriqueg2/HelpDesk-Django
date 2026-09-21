// Executa antes da página para restaurar o tema sem piscar entre claro e escuro.
try {
  const tema = localStorage.getItem('helpdesk_theme');
  document.documentElement.dataset.theme = tema === 'dark' ? 'dark' : 'light';
} catch (_) { /* O portal continua funcionando sem armazenamento local. */ }
