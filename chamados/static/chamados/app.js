document.querySelectorAll('[data-theme-toggle]').forEach(button => {
  button.addEventListener('click', () => {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('helpdesk_theme', theme); } catch (_) {}
  });
});
document.querySelector('[data-password-toggle]')?.addEventListener('click', event => {
  const input = document.getElementById('id_password');
  input.type = input.type === 'password' ? 'text' : 'password';
  event.currentTarget.textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
});
async function checkConnection() {
  const status = document.getElementById('connection-status');
  if (!status) return;
  try {
    const response = await fetch('/api/status', {cache: 'no-store'});
    const data = await response.json();
    status.textContent = response.ok && data.bancoConectado ? 'Sistema conectado' : 'Banco de dados indisponível';
  } catch (_) { status.textContent = 'Sem conexão com o servidor'; }
}
checkConnection();
setInterval(checkConnection, 60000);

async function checkNotifications() {
  const badges = document.querySelectorAll('[data-notification-count]');
  if (!badges.length) return;
  try {
    const response = await fetch('/notificacoes/contagem', {cache: 'no-store'});
    if (!response.ok || response.redirected) return;
    const data = await response.json();
    badges.forEach(badge => { badge.textContent = data.naoLidas; });
  } catch (_) { /* A próxima consulta tentará novamente. */ }
}
setInterval(checkNotifications, 30000);
