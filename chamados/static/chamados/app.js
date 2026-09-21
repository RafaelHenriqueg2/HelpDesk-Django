// Os atributos HTML e os valores light/dark são contratos da interface existente.
document.querySelectorAll('[data-theme-toggle]').forEach(botao => {
  botao.addEventListener('click', () => {
    const tema = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = tema;
    try { localStorage.setItem('helpdesk_theme', tema); } catch (_) {}
  });
});
document.querySelector('[data-password-toggle]')?.addEventListener('click', evento => {
  const campoSenha = document.getElementById('id_senha');
  if (!campoSenha) return;
  campoSenha.type = campoSenha.type === 'password' ? 'text' : 'password';
  evento.currentTarget.textContent = campoSenha.type === 'password' ? 'Mostrar' : 'Ocultar';
});
// Atualiza o indicador sem recarregar a página nem interferir nos formulários.
async function verificarConexao() {
  const indicador = document.getElementById('connection-status');
  if (!indicador) return;
  try {
    const resposta = await fetch('/api/status', {cache: 'no-store'});
    const dados = await resposta.json();
    indicador.textContent = resposta.ok && dados.bancoConectado ? 'Sistema conectado' : 'Banco de dados indisponível';
  } catch (_) { indicador.textContent = 'Sem conexão com o servidor'; }
}
verificarConexao();
setInterval(verificarConexao, 60000);

async function verificarNotificacoes() {
  const contadores = document.querySelectorAll('[data-notification-count]');
  if (!contadores.length) return;
  try {
    const resposta = await fetch('/notificacoes/contagem', {cache: 'no-store'});
    // Uma sessão expirada pode redirecionar ao login e devolver HTML em vez de JSON.
    if (!resposta.ok || resposta.redirected) return;
    const dados = await resposta.json();
    contadores.forEach(contador => { contador.textContent = dados.naoLidas; });
  } catch (_) { /* A próxima consulta tentará novamente. */ }
}
setInterval(verificarNotificacoes, 30000);
