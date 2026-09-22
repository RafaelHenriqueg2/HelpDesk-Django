# Mapeamento da conversão

## Base Django usada

O arquivo `django crud.zip` contém `manage.py`, o projeto `biblioteca`, o app `livros`, ModelForms, views de função e templates com herança de `base.html`.

Foram mantidos `manage.py`, `biblioteca/__init__.py`, `biblioteca/asgi.py` e `biblioteca/wsgi.py`. `settings.py` e `urls.py` foram adaptados. O padrão de formulário, view, template, mensagens de sucesso e redirecionamento do CRUD foi utilizado no HelpDesk.

O app de exemplo `livros` foi substituído por `chamados`. Seu banco, bytecode e telas de livros não fazem parte da aplicação final, pois não pertencem ao domínio HelpDesk. A declaração inconsistente “gerado por Django 6.1” no arquivo da base foi substituída por configuração para Django 5.2.

## Correspondência funcional

| Original | Django |
|---|---|
| NestJS `main.ts`, `app.module.ts` | `biblioteca/settings.py`, `urls.py`, WSGI/ASGI |
| Prisma ORM, schema e migrations | `chamados/models.py` e `migrations/0001_initial.py` |
| `User` | `Usuario`, UUID, e-mail único sem distinguir maiúsculas, perfil e estado ativo |
| `Ticket` | `Chamado`, UUID público e sequencial automático `numero` |
| `Attachment` | `Anexo`, FileField privado e metadados |
| `RegistroLogin` | `RegistroLogin` |
| `MensagemChamado` | `MensagemChamado` |
| AuthService e estratégia JWT | `services.entrar`, `authentication.BearerAuthentication`, `LoginAPI` |
| Guards de autenticação/perfil | `login_required`, `admin_required`, permissões da API |
| DTOs | Forms/ModelForms usados por HTML e API |
| UsersService | `UsuarioForm`, `UsuarioManager`, views e endpoints administrativos |
| TicketsService | `services.py` |
| Upload local e download autenticado | Validação de upload + armazenamento privado + FileResponse |
| HealthController | `HealthAPI`, `/api/status` |
| Seed administrador | `manage.py criar_admin` |
| Frontend `/` | View `inicio`, redireciona conforme perfil |
| Frontend `/login` | Template `login.html` |
| Frontend `/home` | Template `lista.html`, dados limitados ao dono |
| Frontend `/tickets/new` | Template `form.html`, `ChamadoForm` |
| Frontend `/tickets/[id]` | Template `detalhe.html`, anexos, conversa e status |
| Frontend `/admin` | Dashboard com todos os chamados e indicadores |
| Frontend `/admin/users` | `usuarios.html`, cadastro e consulta |
| Header | Navegação e sessão em `base.html` |
| TicketCard | Cartões em `lista.html` |
| ThemeToggle | `theme.js`, `app.js` |
| ConnectionStatus | `/api/status` e indicador em `app.js` |
| `ticket-utils.ts` | Propriedade `protocolo`, choices e filtros de data Django |
| `globals.css` | Copiado para `static/chamados/style.css` |
| `iniciar.cmd` | Inicializa o servidor Django; Ctrl+C encerra na mesma janela |

## Decisões de adaptação

- A interface é renderizada por Django, como no CRUD fornecido. React/Next.js não é necessário para executá-la.
- A interface usa sessões Django; JWT permanece disponível na API. Tokens antigos do NestJS não são reutilizados.
- O vocabulário da API é preservado: `subject`, `sequenceNumber`, `createdAt`, `conteudo`, etc. Os modelos internos usam nomes em português.
- Os endpoints preservam os caminhos sem barra final do original. Identificadores UUID inválidos retornam 404 no roteamento Django; o original retornava 400. Erros de validação retornam 400 com `statusCode` e `message`.
- O login retorna 200 com `accessToken` e `user`. Criações retornam 201. Cookies de sessão não autenticam a API. O projeto final usa mesma origem para páginas e servidor; integração com um frontend externo pode exigir CORS.
- O dashboard administrativo usa cartões com link para o atendimento; a mudança de status fica nos detalhes.
- Senhas novas usam PBKDF2 nativo, com validação de senhas fracas. A base original usava bcrypt. Nenhuma senha ou conta do banco remoto foi importada.
- O protocolo usa incremento gerenciado pelo banco, mantendo UUID como identificador externo. Números não são calculados por contagem e podem apresentar lacunas, como sequências de banco em geral.
- A área técnica Django Admin está em `/django-admin/`, preservando `/admin` para o dashboard do HelpDesk.
- Acrescentados histórico de status, tela de auditoria e paginação das telas.

## Dados e pendências originais

Esta migração cobre o código e as funcionalidades existentes no commit registrado. Os bancos da base de livros e do HelpDesk original não foram fundidos. A versão final inicia com um banco Django novo.

Supabase Storage e filtros de indicadores por período estavam no roadmap; não são apresentados como concluídos nesta entrega. O armazenamento local privado existente foi preservado. O histórico de status do roadmap foi implementado.

Para transportar registros de uma instalação anterior, será necessário um backup/exportação das tabelas Prisma e dos arquivos originais, mapear UUIDs, números de protocolo, datas e hashes, e ajustar a sequência do novo banco. Isso não foi executado sem esses dados.
