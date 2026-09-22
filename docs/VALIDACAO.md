# Validação da entrega

## Limpeza do código — 22/09/2026

- Windows, Python 3.14.7 e dependências de `requirements-cloud-lock.txt` instaladas.
- 73 testes passaram com SQLite, sem testes pulados.
- `manage.py check`, `makemigrations --check --dry-run`, `pip check` e análise Ruff (regras F) passaram.
- Seletores CSS removidos foram conferidos contra Python, JavaScript e templates; classes dinâmicas de status/urgência e `errorlist` gerada pelo Django foram preservadas. Declarações, ordem e condições de mídia dos seletores mantidos foram comparadas automaticamente.
- Nenhum modelo ou arquivo de migration foi alterado. Nenhum acesso ao Supabase real foi feito nesta revisão; o teste S3 verifica o bloqueio de URLs públicas sem upload remoto.
- Detalhes da limpeza e justificativas: [LIMPEZA.md](LIMPEZA.md).

## Identificadores em português e comentários — 20/09/2026

- 73 testes passaram em SQLite e PostgreSQL 18 isolado.
- Cobertura adicional: cadastro e login em português, entradas antigas, paginação HTML, comando createsuperuser e migração reversível preservando contas excluídas e vínculos.
- A migration 0005 foi aplicada localmente após backup; todos os registros de todas as tabelas existentes foram comparados antes/depois e preservados.
- Exportação/importação entre bancos PostgreSQL isolados novamente validada.
- Portal conferido no navegador: sessão existente, nomes, perfis e campos traduzidos.
- Rotas e chaves JSON da API permanecem compatíveis; as novas exportações JSON usam os campos internos traduzidos.

## Evolução de atendimento e preparação para Supabase — 20/09/2026

- 67 testes passaram em SQLite e PostgreSQL 18 isolado, incluindo os testes anteriores.
- Schema PostgreSQL exclusivo com 18 tabelas: preparação e migrations validadas.
- Exportação/importação entre dois bancos isolados preservou UUIDs, protocolos, usuários e relacionamentos; sequência numérica validada após importação.
- Check do Django, consistência de migrations e pip check sem erros.
- Portal local atualizado e conferido no navegador: estados, prazos, responsável, categoria, notas internas, anexos e navegação.
- Banco local preservado. Credenciais e conexão real com Supabase não foram fornecidas; serviço remoto, armazenamento S3 real e hospedagem web permanecem sem ativação.
- A paginação citada na revisão anterior foi implementada. Limitação de tentativas de login e revogação de JWT por mudança de senha continuam sendo pendências anteriores à publicação na internet.

Os relatos seguintes registram as rodadas anteriores.

## Revisão local em 20/09/2026

- 40 testes passaram em SQLite: 28 existentes e 12 novos para exclusão de usuários.
- `manage.py check`: sem erros; `makemigrations --check --dry-run`: sem alterações pendentes.
- Migration 0002 aplicada ao banco local após cópia de segurança; contas e atendimentos existentes preservados.
- Testes novos verificam: preservação de mensagens/anexos/histórico/auditoria; retirada das listas; e-mail reservado; revogação de sessão/token após exclusão; permissões; autoexclusão; proteção de contas técnicas; confirmação/CSRF; exclusão repetida; administrador com dados de sessão desatualizados; restrição do banco contra reativação; bloqueios no Django Admin e no comando criar_admin.
- Navegador: login, lista com ação Excluir, confirmação com identificação da conta e cancelamento. A exclusão completa foi validada no banco isolado de testes, sem excluir as contas de demonstração.
- Três verificações exploratórias em banco isolado confirmaram pendências: JWT continua válido após trocar a senha; 25 logins incorretos consecutivos sem bloqueio; API devolve 45 chamados mesmo com page=1. Esses resultados confirmam problemas, não correções.
- Esta rodada usou Python 3.12, Django 5.2.17 e DRF 3.18.1. Não houve execução contra PostgreSQL, testes de carga, auditoria de vulnerabilidades das dependências nem validação de infraestrutura de produção.

Os registros abaixo descrevem a validação original do ZIP.

## Ambiente

- Windows, Python 3.14.7.
- Django 5.2.17, Django REST Framework 3.18.1.
- SQLite, banco de testes separado e uploads em diretórios temporários.
- Dependências registradas em `requirements-lock.txt`.

## Verificações executadas

- `manage.py check`: sem erros.
- `manage.py migrate`: todas as migrations aplicadas em banco novo.
- `manage.py test chamados`: **28 testes passaram**.
- Navegador local: login com conta fictícia, dashboard, detalhe de chamado, alteração de status e envio de mensagem; resultado conferido na interface.
- Inspeção visual das telas de login, dashboard e detalhes em viewport desktop.

## Cobertura funcional dos testes

- Login válido/inválido, normalização de e-mail e registro de auditoria.
- JWT expirado/malformado, usuário desativado e mudança de perfil após emissão.
- Rotas protegidas sem autenticação.
- Cadastro/lista/detalhe de usuários, hash de senha, duplicidade e senha fraca.
- Bloqueio de administração para usuário comum.
- Abertura e protocolo sequencial; dono e status não controlados pelo cliente.
- Listagem/detalhe limitados ao proprietário; administrador acessa todos.
- Mudanças de status, resolução, reabertura e histórico sem entradas duplicadas.
- Conversa do usuário com administrador; rejeição de mensagem vazia e intrusão.
- Upload/download privados e vínculo do anexo ao chamado correto.
- Rejeição de arquivo inexistente, extensão inválida, imagem falsa e tamanho excedido.
- PDF permitido e upload válido acima do limite de arquivo em memória do Django.
- Rollback do chamado e remoção do arquivo em falha de gravação.
- Health check com sucesso e indisponibilidade simulada do banco.
- Renderização das telas HTML para os perfis corretos e tela técnica de cadastro.
- CSRF, login HTML, criação, mensagem, logout somente POST.
- Busca por protocolo, filtro de status e escape de HTML na descrição.
- Tentativas de acesso HTML por outro usuário e JSON malformado.

## Limites da validação

Não foram executados testes contra PostgreSQL/Supabase, armazenamento remoto, infraestrutura de produção, carga concorrente ou importação dos dados reais. O ZIP não inclui bancos, credenciais ou anexos do usuário. Supabase Storage continua uma evolução futura conforme o escopo original.
