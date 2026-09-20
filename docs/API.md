# API REST

Atualização de atendimento: as listagens de usuários/chamados são paginadas e retornam `results`. Novos endpoints, campos e regras estão em [ATENDIMENTO.md](ATENDIMENTO.md). Resolver agora exige `solucao`; cancelar ou reabrir pela alteração de status exige `motivo`.

Base local: `http://127.0.0.1:8000/api`. Caminhos sem barra final.

## Endpoints

| Método | Rota | Acesso |
|---|---|---|
| GET | `/api/status` | Público |
| POST | `/api/auth/login` | Público |
| GET | `/api/auth/me` | JWT |
| POST | `/api/users` | ADMIN |
| GET | `/api/users` | ADMIN |
| GET | `/api/users/{uuid}` | ADMIN |
| DELETE | `/api/users/{uuid}` | ADMIN, sujeito às proteções abaixo |
| POST | `/api/chamados` | JWT |
| GET | `/api/chamados` | JWT, escopo do usuário |
| GET | `/api/chamados/{uuid}` | Dono ou ADMIN |
| PATCH | `/api/chamados/{uuid}/status` | ADMIN |
| POST | `/api/chamados/{uuid}/mensagens` | Dono ou ADMIN |
| GET | `/api/chamados/{uuid}/anexos/{anexo_uuid}` | Dono ou ADMIN |

## Login

### Exclusão de conta

`DELETE /api/users/{uuid}` retorna 204 sem corpo. Remove a conta das listagens e consultas individuais de usuários, bloqueia acesso e preserva todos os atendimentos e a identificação histórica. Não permite autoexclusão (400); usuário comum não pode excluir (403); contas técnicas exigem outro superusuário (403 se não autorizado). Conta inexistente ou já excluída retorna 404. Sem autenticação válida, retorna 401. O e-mail continua reservado.

### Credenciais

```http
POST /api/auth/login
Content-Type: application/json

{"email":"seu-email@exemplo.com","password":"SUA_SENHA"}
```

Resposta: `{"accessToken":"...","user":{"id":"...","name":"...","email":"...","role":"ADMIN","active":true,"createdAt":"...","updatedAt":"..."}}`.

Nas próximas requisições: `Authorization: Bearer SEU_TOKEN`.

O token expira após 8 horas por padrão, configurável por `JWT_EXPIRES_SECONDS`. Desativar uma conta ou mudar seu perfil passa a valer imediatamente, porque a autorização consulta o banco. Como no original, não há endpoint de refresh ou lista de revogação individual de JWT; para sair de um cliente API, descarte seu token.

## Criar usuário

```json
{
  "name": "Maria Silva",
  "email": "maria@exemplo.com",
  "password": "UMA_SENHA_FORTE",
  "role": "USER"
}
```

`role` é opcional, com padrão `USER`. Nome: 2–120 caracteres; e-mail: até 180; senha: 8–72, sujeita aos validadores Django. E-mails são normalizados para minúsculas. A resposta pública nunca inclui hash ou senha.

## Abrir chamado

Envie `multipart/form-data` com:

- `assunto`: 3–150 caracteres.
- `descricao`: 10–5000 caracteres.
- `urgencia`: `LOW`, `MEDIUM`, `HIGH` ou `CRITICAL`.
- `anexo`: opcional, PNG/JPG/PDF, até 5 MiB.

Sem arquivo, JSON com os mesmos campos também é aceito. `userId` e `status` enviados pelo cliente não alteram o dono nem o status inicial.

Resposta:

```json
{
  "id": "UUID_DO_CHAMADO",
  "sequenceNumber": 1,
  "subject": "Falha na impressora",
  "description": "A impressora não imprime documentos.",
  "urgency": "HIGH",
  "status": "OPEN",
  "createdAt": "DATA_ISO",
  "updatedAt": "DATA_ISO",
  "user": {"name": "Maria Silva", "email": "maria@exemplo.com"},
  "attachments": [{"id": "UUID_DO_ANEXO", "fileName": "erro.png", "size": 1000}]
}
```

Detalhes incluem `mensagens`, em ordem cronológica, com `id`, `conteudo`, `criadoEm` e `autor: {name, role}`.

## Alterar status e conversar

```http
PATCH /api/chamados/UUID/status
Authorization: Bearer TOKEN_ADMIN
Content-Type: application/json

{"status":"IN_PROGRESS"}
```

Status aceitos: `OPEN`, `IN_PROGRESS`, `RESOLVED`.

```http
POST /api/chamados/UUID/mensagens
Authorization: Bearer TOKEN
Content-Type: application/json

{"conteudo":"O problema continua acontecendo."}
```

Mensagem: 1–2000 caracteres após remover espaços nas extremidades. Autor e chamado são definidos pelo servidor.

## Exemplo no PowerShell

```powershell
$credenciais = @{email='seu-email@exemplo.com'; password='SUA_SENHA'} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/login -ContentType application/json -Body $credenciais
$cabecalhos = @{Authorization="Bearer $($login.accessToken)"}
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chamados -Headers $cabecalhos
```

## Respostas de erro

- 400: dados inválidos ou JSON malformado.
- 401: login inválido, token ausente, inválido, expirado ou conta desativada.
- 403: ação administrativa com perfil insuficiente.
- 404: recurso inexistente, UUID malformado ou chamado/anexo fora do escopo da conta.
- 409: conflito de e-mail detectado durante gravação concorrente. Duplicata detectada no formulário retorna 400.
- 503: banco indisponível no health check.

Erros tratados pela API retornam `{"statusCode":400,"message":["Descrição do erro"]}`; `message` pode ser uma string. Rotas não reconhecidas pelo Django retornam sua página 404.
