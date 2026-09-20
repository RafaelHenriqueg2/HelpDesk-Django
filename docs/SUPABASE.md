# Banco compartilhado com Supabase
O projeto está preparado para PostgreSQL e Supabase Storage privado. A conexão real depende de um projeto Supabase e das credenciais do proprietário. Nenhuma conta/projeto Supabase foi criada e os dados locais ainda não foram enviados.

## O que será compartilhado
O PostgreSQL guarda usuários, chamados, mensagens, histórico e notificações. O Storage guarda o conteúdo dos anexos. Usar apenas banco remoto com pastas de upload diferentes em cada computador faz os anexos faltarem em outras instâncias.

Supabase não publica automaticamente as páginas Django. Para as pessoas entrarem por um endereço da internet, a aplicação também precisa ser hospedada. Não exponha o servidor runserver como servidor de produção.

## Preparar o serviço
1. Crie um projeto Supabase destinado ao HelpDesk e guarde a senha do banco.
2. Em Connect, copie a URI PostgreSQL de conexão direta ou Session pooler. Para um computador sem IPv6, o Session pooler é a alternativa indicada na documentação. Não use Transaction pooler neste procedimento.
3. Crie um bucket **privado** chamado helpdesk-anexos.
4. Na configuração S3 do Storage, gere as credenciais e copie endpoint e região. Essas credenciais ficam somente no servidor.
5. Não adicione o schema helpdesk aos schemas expostos pela API de dados do Supabase. Os usuários entram pela autenticação Django; não precisam de acesso direto ao PostgreSQL nem de chaves do Supabase.

Referências: [conexão PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres), [credenciais S3](https://supabase.com/docs/guides/storage/s3/authentication) e [backend django-storages](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html).

## Configurar localmente
Na pasta do projeto:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cloud.txt
Copy-Item .env.supabase.example .env.supabase
code .env.supabase
```

Preencha DATABASE_URL, SECRET_KEY, endpoint/região/bucket e credenciais S3. Não envie as senhas no chat. A senha na URI precisa ter caracteres especiais codificados. Use a mesma SECRET_KEY em todas as instâncias; você pode reutilizar o segredo atual guardado localmente em .django-secret. Não copie esse segredo para documentação ou repositórios.

O arquivo .env.supabase é ignorado pelo Git. SHARED_DATABASE=True exige PostgreSQL, URI preenchida, segredo explícito e TLS; uma configuração incompleta não muda silenciosamente para SQLite. O comando de preparação cria um schema separado e retira acesso dos papéis públicos anon/authenticated, quando eles existem.

## Levar os dados atuais
Interrompa gravações durante exportação/importação, mantenha o backup local e use um projeto de destino novo.

Primeiro exporte ainda com o ambiente local:
```powershell
Remove-Item Env:HELPDESK_ENV_FILE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe manage.py exportar_dados backups\helpdesk.backup.json
```
Se DATABASE_URL estiver definido no terminal, remova essa variável ou confira o destino antes de exportar: variáveis de ambiente têm precedência sobre os arquivos .env.

Depois selecione a configuração Supabase:
```powershell
$env:HELPDESK_ENV_FILE = (Resolve-Path .env.supabase).Path
.\.venv\Scripts\python.exe manage.py preparar_banco_compartilhado
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py importar_dados backups\helpdesk.backup.json
.\.venv\Scripts\python.exe manage.py copiar_anexos private_uploads
.\.venv\Scripts\python.exe manage.py check
```

A importação recusa um destino com usuários/chamados ou categorias personalizadas. As categorias padrão de uma instalação nova são substituídas pelas exportadas dentro da transação. UUIDs, protocolos, senhas com hash e relacionamentos são mantidos; sessões existentes não são exportadas, então será necessário entrar novamente.

A cópia de anexos preserva a origem e não sobrescreve objetos já existentes. Confira uploads e downloads com uma conta de administrador e uma de usuário comum antes de liberar acesso.

Para validar localmente usando o banco remoto:
```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
Não execute preparar_demo ou criar_admin no destino se já importou as contas atuais.

## Publicação da aplicação
Configure DEBUG=False, domínio em ALLOWED_HOSTS, HTTPS e CSRF_TRUSTED_ORIGINS. Use um servidor WSGI/ASGI apropriado, execute collectstatic e mantenha credenciais exclusivamente no ambiente do servidor. O projeto contém configuração de banco/storage; nenhuma hospedagem web foi contratada ou publicada.

Antes da exposição pública, trate também as pendências da revisão anterior: limitação de tentativas de login e revogação do JWT quando a senha muda. A paginação foi implementada nesta atualização.

## Validação executada
- 67 testes em SQLite e PostgreSQL 18 local isolado.
- Criação de schema privado e aplicação das migrations nesse schema.
- Exportação/importação entre bancos de teste, com checagem de UUIDs, protocolos e relacionamentos.
- Backend de storage privado configurado; geração de URL pública bloqueada.
- A conexão real e os uploads para Supabase Storage ainda dependem das credenciais e não foram exercitados.
