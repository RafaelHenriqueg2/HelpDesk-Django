# HelpDesk em Django

## Código em português e comentado

Classes, variáveis e campos próprios usam nomes em português. Consulte o [guia de leitura do código](docs/CODIGO_COMENTADO.md). A migration 0005 preserva os dados ao renomear os campos de usuários.

## Atualização: atendimento completo e banco compartilhado

Foram adicionados responsável, categorias, novos estados, confirmação/reabertura, prazos, notas internas, múltiplos anexos, notificações no portal, incidentes relacionados e histórico completo. Veja [o guia de atendimento](docs/ATENDIMENTO.md).

O projeto está preparado para PostgreSQL/Supabase e armazenamento privado de anexos. A conexão com a sua conta ainda precisa ser configurada: [passo a passo](docs/SUPABASE.md). O ambiente atual continua local.

A suite atual tem **73 testes**, executados com SQLite e PostgreSQL 18 local. As listagens da API agora retornam um objeto paginado com `results`; veja as alterações de contrato em [ATENDIMENTO.md](docs/ATENDIMENTO.md).

Conversão do projeto [samuelcorazzi/HelpDesk](https://github.com/samuelcorazzi/HelpDesk), usando o **`django crud.zip` fornecido como base estrutural**.

O sistema inteiro roda em uma aplicação Django: páginas HTML, autenticação, API, banco e anexos. Não é necessário executar Node.js, Next.js, NestJS ou Prisma.

## Executar no Windows

1. Extraia o ZIP em uma pasta.
2. Instale Python 3.10 ou superior, com a opção **Add Python to PATH**.
3. Abra **`iniciar.cmd`**.
4. Na primeira execução, informe nome, e-mail e senha para criar seu administrador. A senha não aparece enquanto você digita.
5. Acesse **http://127.0.0.1:8000** e entre com a conta criada.

O inicializador cria `.venv`, instala as dependências, prepara o SQLite e aplica as migrations. A primeira execução precisa de internet para instalar os pacotes. As contas, chamados e anexos persistem entre execuções.

Para parar, pressione **Ctrl+C** na janela do servidor.

## Instalação manual

No PowerShell, dentro da pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py criar_admin
.\.venv\Scripts\python.exe manage.py runserver
```

Não é necessário ativar o ambiente virtual, evitando problemas com a política de execução do PowerShell.

Em Linux/macOS, substitua `.\.venv\Scripts\python.exe` por `.venv/bin/python` e use `cp .env.example .env`.

### Demonstração para apresentação

Em uma instalação local com migrations aplicadas:

```powershell
.\.venv\Scripts\python.exe manage.py preparar_demo
```

O comando cria dois usuários fictícios, três chamados e uma conversa. Exibe **senhas aleatórias**, que devem ser guardadas. Não altera contas já existentes e só funciona com `DEBUG=True`. O ZIP não contém contas ou senhas prontas.

### Administrador inicial e recuperação local

Também é possível usar `python manage.py createsuperuser`. O comando `criar_admin` aceita `--email`, `--nome` e as variáveis `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_NAME`, `INITIAL_ADMIN_PASSWORD`. Para alterar explicitamente a senha de uma conta existente e torná-la administradora:

```powershell
.\.venv\Scripts\python.exe manage.py criar_admin --email admin@exemplo.com --atualizar-senha
```

O administrador inicial acessa a área técnica `/django-admin/`, onde pode ativar/desativar contas. Um administrador cadastrado pelo portal recebe o perfil `ADMIN` para atendimento, sem receber automaticamente poderes de superusuário no Django Admin.

## Funcionalidades

### Usuário

- Login por e-mail e senha e saída segura por POST.
- Listagem exclusiva dos próprios chamados.
- Busca por assunto ou protocolo, filtro de status e paginação.
- Abertura com assunto, descrição, urgência e anexo opcional.
- Protocolo sequencial automático: `HD-000001`.
- Detalhes, situação e datas do atendimento.
- Conversa com a equipe de suporte.
- Download privado de anexos.

### Administrador

- Painel com todos os chamados e indicadores por status.
- Busca também pelo nome/e-mail do solicitante.
- Cadastro, listagem e consulta de usuários.
- Exclusão de contas pelo portal e pela API, preservando os atendimentos e registrando o responsável.
- Alteração de status: aberto, em atendimento, aguardando usuário/terceiro, resolvido, encerrado e cancelado.
- Registro/limpeza da data de resolução ao resolver/reabrir.
- Conversa com solicitantes e download de anexos.
- Consulta da auditoria de login.
- Histórico de alterações de status, acrescentado nesta versão.

### Interface

- Identidade visual e CSS reutilizados do repositório original.
- Templates Django substituem as páginas React.
- Tema claro/escuro, mostrar/ocultar senha e indicador de conexão.
- Navegação adaptada a telas menores.
- Formulários funcionam sem JavaScript; o JavaScript cuida do tema, da senha e do indicador de conexão.

## Estrutura

```text
HelpDesk-Django/
├── manage.py                 # Mantido da base fornecida
├── biblioteca/               # Projeto Django da base, adaptado
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── chamados/                 # Domínio HelpDesk substitui o exemplo livros
│   ├── models.py             # Usuários, chamados, anexos, conversa, auditoria
│   ├── forms.py              # ModelForms e validações
│   ├── services.py           # Regras compartilhadas entre HTML e API
│   ├── views.py              # Telas no padrão de views do CRUD fornecido
│   ├── authentication.py     # JWT para clientes da API
│   ├── api.py                # Endpoints REST
│   ├── urls.py
│   ├── api_urls.py
│   ├── admin.py
│   ├── migrations/
│   ├── management/commands/  # criar_admin, preparar_demo
│   ├── templates/            # base, login, dashboard, detalhes, usuários
│   ├── static/chamados/      # CSS original e adaptações Django
│   └── tests.py
├── docs/
│   ├── MIGRACAO.md           # Correspondência entre os dois projetos
│   ├── API.md                # Contratos e exemplos
│   └── VALIDACAO.md
├── .env.example
├── requirements.txt
├── requirements-lock.txt    # Versões usadas nos testes em Windows/Python 3.14
├── iniciar.cmd
└── parar.cmd
```

## Banco de dados

### SQLite local

É o padrão. Não exige PostgreSQL, conta Supabase ou credenciais. `manage.py migrate` cria `db.sqlite3`.

### PostgreSQL / Supabase

Configure `DATABASE_URL` em `.env`, apontando para um **banco novo destinado a esta versão Django**:

```dotenv
DATABASE_URL=postgresql://USUARIO:SENHA@HOST:5432/helpdesk_django?sslmode=require
```

Use uma conexão direta ou session pooler compatível com migrations; codifique caracteres especiais da senha na URL. Depois execute `python manage.py migrate` e crie o administrador nesse banco.

**A conversão é do código e das funcionalidades. Os dados existentes do banco Prisma/Supabase não foram importados.** Não foram fornecidos backup ou acesso ao banco original. As tabelas Django são novas e não substituem automaticamente as tabelas Prisma. Não reaproveite o `db.sqlite3` do CRUD de livros.

O caminho PostgreSQL está configurado, mas a validação realizada nesta entrega foi com SQLite. A conexão com seu Supabase depende das suas credenciais e da configuração do serviço.

## Anexos

- O campo é opcional e aceita PNG, JPG/JPEG e PDF de até 5 MiB (`5 × 1024 × 1024` bytes).
- Imagens são verificadas com Pillow; PDF é validado por extensão e assinatura inicial. Isso não é uma varredura antivírus.
- Nomes internos são aleatórios e os nomes originais são preservados para download.
- Os arquivos ficam em `private_uploads/anexos/` e são servidos exclusivamente por views autenticadas.
- Não há rota pública `/media/`. Não publique `private_uploads` diretamente em um servidor web.
- O download exige que a conta seja dona do chamado ou administradora.
- Se a gravação do banco falhar, o arquivo recém-gravado é removido.

Supabase Storage constava como **pendente** no projeto original. Esta entrega preserva o armazenamento local privado. Para múltiplas instâncias em produção, será necessário configurar armazenamento privado compartilhado.

## Autenticação e segurança

As páginas usam sessões Django com cookie HttpOnly e CSRF em operações POST. A API usa `Authorization: Bearer TOKEN_JWT`, com expiração padrão de 8 horas. Ela não aceita o cookie de sessão como substituto do token.

O papel e o estado ativo são consultados no banco a cada requisição autenticada. O cliente não escolhe o autor do chamado ou da mensagem. Senhas novas usam o hash PBKDF2 do Django; hashes e caminhos internos não aparecem nas respostas públicas. A auditoria registra e-mail, sucesso/falha, IP do par conectado, navegador e data, sem registrar a senha digitada.

O segredo de desenvolvimento é gerado em `.django-secret` e ignorado pelo Git. Em produção, `SECRET_KEY` é obrigatório. Nunca versione `.env`, bancos locais, uploads ou chaves.

## Testes e verificação

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test chamados
```

Foram executados **67 testes automatizados**, com SQLite e PostgreSQL local, cobrindo autenticação, autorização, chamados, anexos, mensagens, exclusão de contas e os novos fluxos de atendimento. Veja `docs/ATENDIMENTO.md`.

### Exclusão de usuários

Na página Usuários, clique em Excluir e confirme a conta selecionada. A exclusão remove a conta das listas do portal/API, desativa o acesso e inutiliza a senha; sessões e tokens anteriores deixam de autenticar. Chamados, anexos, mensagens, identificação do autor e auditoria permanecem disponíveis.

O administrador não pode excluir a própria conta. Contas com acesso técnico (staff/superusuário) só podem ser excluídas por outro superusuário. A data e o responsável ficam registrados em `excluido_em` e `excluido_por`, visíveis na administração técnica. Contas excluídas são somente leitura nessa área, e a exclusão física por Django Admin está desabilitada.

O e-mail permanece reservado; esta operação não anonimiza dados e não oferece restauração pelo portal. A migration `0002_exclusao_logica_usuario` atualiza instalações existentes sem excluir seus registros.

## Publicação

`runserver` e `iniciar.cmd` destinam-se ao desenvolvimento. Para hospedar:

1. Configure `DEBUG=False`, `SECRET_KEY` aleatório e `ALLOWED_HOSTS` com seu domínio.
2. Configure PostgreSQL, HTTPS e `CSRF_TRUSTED_ORIGINS` se necessário.
3. Execute migrations e `python manage.py collectstatic`.
4. Use servidor WSGI/ASGI adequado para seu ambiente com `biblioteca.wsgi:application` ou `biblioteca.asgi:application`.
5. Sirva somente os arquivos estáticos publicamente; mantenha uploads privados.
6. Configure backup do banco e anexos e controles de tráfego para login/upload conforme o ambiente.

O sistema não foi publicado nem alterou o repositório remoto.

## Referências

- [Projeto original HelpDesk](https://github.com/samuelcorazzi/HelpDesk), commit `cddf8549bdcd550eb97215efa99d4cd243ecdcfb`.
- Base local: `django crud.zip`, projeto `crud/biblioteca` e app de exemplo `livros`.
- [Django 5.2: notas e compatibilidade de Python](https://docs.djangoproject.com/en/5.2/releases/5.2/).
