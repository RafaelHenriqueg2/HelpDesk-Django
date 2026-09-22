# Interface do portal

A renovação visual das telas internas fica em `chamados/static/chamados/portal.css`. Os seletores usam o escopo `.app-shell`, e o arquivo não é carregado na rota de login. O template de login e seus estilos foram preservados nesta etapa.

## Organização

- `templates/base.html`: navegação, cabeçalho, área de conteúdo e opção de tema.
- `templates/chamados/icon.html`: ícones SVG locais, sem biblioteca externa.
- `templates/chamados/lista.html`: indicadores, busca, filtros e cartões de chamados.
- `templates/chamados/detalhe.html`: conversa, ações e histórico, com resumo lateral do atendimento.
- `templates/chamados/form.html`: formulário de abertura e orientações de preenchimento.
- Telas de usuários, auditoria e notificações compartilham a mesma linguagem visual.

O portal usa uma pilha de fontes do sistema, começando por Segoe UI Variable/Segoe UI no Windows. Não faz requisições a provedores externos de fontes. Cores e superfícies são definidas por variáveis CSS para os temas claro e escuro.

## Responsividade e acessibilidade

A navegação muda em telas pequenas, os indicadores ficam em duas colunas e as tabelas têm rolagem própria. Campos de formulário usam texto de 16px no celular. Links e botões possuem foco visível; há um atalho para pular a navegação, rótulos nos campos, títulos das colunas e suporte à preferência por movimento reduzido. Status continuam identificados por texto, além de cor.

## Validação

- 73 testes existentes passaram após a alteração dos templates.
- `manage.py check` sem problemas.
- Conferência no navegador de painel, filtros sem resultados, detalhes, abertura de chamado, usuários e notificações; tema claro/escuro e viewport de celular de 390px.
- Dados de demonstração ficaram em SQLite separado, fora do repositório. Nenhum acesso ao Supabase real foi feito.

As regras de negócio, rotas, proteção CSRF, contratos da API e integração com Supabase permanecem os mesmos. Nenhum pacote de frontend ou etapa de compilação foi adicionado.
