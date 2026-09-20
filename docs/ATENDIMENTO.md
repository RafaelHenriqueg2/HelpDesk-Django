# Chamados: funcionalidades e regras
Atualização de 20/09/2026.

## As dez melhorias
1. **Responsável:** na seção Gerenciar atendimento, atribua ou transfira para uma conta ADMIN ativa. O filtro Meus atendimentos mostra os chamados atribuídos à pessoa conectada. Fila sem responsável ajuda na triagem.
2. **Categorias:** Acesso, Computador, Impressora, Internet, Sistemas e Outros. Disponíveis na abertura, gestão e filtros. Um superusuário pode cadastrar/desativar categorias no Django Admin.
3. **Situações:** Aberto, Em atendimento, Aguardando usuário, Aguardando terceiro, Resolvido, Encerrado e Cancelado.
4. **Confirmação:** resolver exige solução com pelo menos 10 caracteres. O solicitante confirma para encerrar ou reabre explicando o problema (5 a 2000 caracteres). O técnico também pode reabrir. Cancelar exige motivo; somente a equipe reabre um cancelamento pela alteração de status.
5. **Prazos:** primeira resposta e resolução em horas corridas, com indicadores de atraso e vencimento em até uma hora.
6. **Notas internas:** na conversa, a equipe pode marcar Nota interna. Conteúdo, anexos, eventos e notificações internos não são apresentados ao solicitante ou a usuários comuns.
7. **Anexos na conversa:** até cinco arquivos por envio; PNG/JPG/PDF, até 5 MiB por arquivo e 20 MiB somados. Todos são validados. Falha de gravação desfaz mensagem/chamado e remove os arquivos recém-criados.
8. **Notificações:** dentro do portal, para solicitante e equipe. Incluem abertura, resposta, atribuição e mudanças de status. O contador é atualizado a cada 30 segundos; abrir o chamado marca as notificações como lidas. A API oferece consulta e marcação individual. Não foi configurado envio por e-mail.
9. **Duplicados:** o administrador vincula um chamado a um incidente principal em atendimento. Não são permitidos ciclos nem cadeias. Resolver o principal comunica a solução e resolve os vinculados que ainda estão em atendimento, deixando a confirmação para cada solicitante. Vinculados já finalizados permanecem como estão. Reabrir o principal não reabre automaticamente os demais. Um usuário comum não ganha acesso ao chamado de outra pessoa.
10. **Histórico completo:** abertura, status, solução, responsável, categoria, urgência, prazos, mensagens/notas, vínculo e reabertura. Notas e vínculos entre incidentes têm histórico restrito à equipe.

## Política inicial de prazos
| Urgência | Primeira resposta | Resolução |
|---|---:|---:|
| Baixa | 24 horas | 72 horas |
| Média | 8 horas | 24 horas |
| Alta | 2 horas | 8 horas |
| Crítica | 30 minutos | 4 horas |

Aguardando usuário pausa os dois prazos ainda pendentes. Quando o solicitante responde, o chamado volta a Em atendimento e os prazos são prorrogados pela duração da pausa. Aguardando terceiro não pausa. Uma nota interna não conta como primeira resposta.

Resolver também conta como primeira resposta, quando ela ainda não existe. Reabrir inicia um novo ciclo de prazos. Alterar urgência não apaga atrasos nem recalcula prazos automaticamente; mudanças manuais de prazo exigem justificativa e ficam no histórico. Não se permite alterar datas durante a pausa.

Os valores estão em SLA_HORAS_JSON no ambiente. Mudanças nessa política valem para novas aberturas/reaberturas, sem reescrever os prazos existentes. Datas antigas de primeira resposta e soluções não foram inventadas durante a migração.

## Perfis
Nesta versão, técnico é uma conta com perfil ADMIN; mantém as permissões administrativas que esse perfil já possuía. Não foi criado um perfil adicional com permissões reduzidas. Usuário comum acessa apenas seus chamados. A confirmação da solução exige ser o solicitante.

## Compatibilidade da API
As listagens GET /api/users e GET /api/chamados passaram a retornar um objeto paginado:
```json
{"count":42,"page":1,"nextPage":2,"previousPage":null,"results":[]}
```
Clientes que esperavam uma lista direta devem ler results. A página tem até 20 registros. Mensagens têm até 30 por página.

Novos endpoints:
- GET /api/categorias
- PATCH /api/chamados/{uuid}/gestao: responsável (UUID), categoria (ID inteiro), urgência, prazo_resposta, prazo_resolucao e motivo; envie somente os campos a alterar.
- PATCH /api/chamados/{uuid}/status: status, solucao e motivo.
- POST /api/chamados/{uuid}/confirmar
- POST /api/chamados/{uuid}/reabrir: motivo.
- PATCH /api/chamados/{uuid}/incidente: incidente recebe o número sequencial inteiro do principal; null desfaz o vínculo.
- GET /api/chamados/{uuid}/historico
- GET /api/chamados/{uuid}/mensagens?page=1
- POST /api/chamados/{uuid}/mensagens: conteudo, interna (booleano) e arquivos repetidos no campo anexo de multipart/form-data.
- GET /api/notificacoes?page=1
- POST /api/notificacoes/{id}/ler

GET /api/chamados aceita status, urgencia e meus=1. O detalhe devolve as últimas 30 mensagens visíveis e mensagensTotal; para as demais, use o endpoint paginado de mensagens. Os downloads continuam passando por autorização no Django.

## Validação
67 testes passaram em SQLite e em uma instância PostgreSQL 18 isolada. Foram cobertos atribuição, permissões, pausas, prazos, confirmação/reabertura, cancelamento, privacidade das notas/anexos, múltiplos uploads, rollback, notificações, duplicados, paginação e os fluxos anteriores.
