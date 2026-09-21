# Guia do código em português

Os identificadores próprios da aplicação foram traduzidos para facilitar o estudo. Os comentários explicam as regras de negócio, os motivos das permissões e os cuidados com os dados.

## Por onde começar

1. `chamados/urls.py`: liga cada endereço do navegador a uma função.
2. `chamados/views.py`: recebe a `requisicao`, valida o `formulario` e monta a página.
3. `chamados/forms.py`: contém `FormularioEntrada`, `FormularioUsuario`, `FormularioChamado` e os demais formulários.
4. `chamados/models.py`: define `Usuario`, `Chamado`, `Categoria`, mensagens, anexos e histórico.
5. `chamados/services.py`: reúne autenticação, permissões e exclusão lógica de usuários.
6. `chamados/fluxo.py`: aplica prazos, notas internas, reabertura e vínculos de incidentes.
7. `chamados/api.py`: transforma registros em respostas JSON compatíveis com a API existente.
8. `chamados/templates/`: apresenta as informações; `static/chamados/` contém o visual e os scripts.

## Exemplos de nomes

| Antes | Agora | Significado |
|---|---|---|
| `UsuarioManager` | `GerenciadorUsuarios` | Criação de contas |
| `ChamadoQuerySet` | `ConsultaChamados` | Consultas com controle de acesso |
| `UsuarioForm` | `FormularioUsuario` | Validação do cadastro |
| `BearerAuthentication` | `AutenticacaoToken` | Autenticação da API |
| `PrivateS3Storage` | `ArmazenamentoPrivadoS3` | Anexos privados na nuvem |
| `request`, `response` | `requisicao`, `resposta` | Entrada e saída de uma página ou API |
| `form`, `qs` | `formulario`, `consulta` | Formulário e consulta ao banco |
| `Usuario.name`, `Usuario.role` | `Usuario.nome`, `Usuario.perfil` | Nome e perfil da conta |
| `created_at`, `updated_at` | `criado_em`, `atualizado_em` | Datas do cadastro |
| `deleted_at`, `deleted_by` | `excluido_em`, `excluido_por` | Exclusão preservando histórico |
| `is_admin` | `eh_administrador` | Verificação de permissão |
| `Chamado.Status.OPEN` | `Chamado.Situacao.ABERTO` | Situação inicial |
| `Chamado.Urgencia.HIGH` | `Chamado.Urgencia.ALTA` | Urgência alta |

## Nomes mantidos por compatibilidade

- Django exige nomes como `Meta`, `objects`, `save`, `clean`, `create_user`, `create_superuser`, `Command`, `handle`, `is_active`, `is_staff` e `password`. Este último guarda o hash; a senha digitada no formulário se chama `senha`.
- Configurações como `DATABASES`, nomes dos módulos convencionais (`models.py`, `views.py`, `forms.py`) e métodos/importações de bibliotecas permanecem conforme suas interfaces oficiais. `self`, `cls`, `args` e `kwargs` seguem a convenção Python.
- As chaves públicas da API, os códigos armazenados (`USER`, `ADMIN`, `OPEN`, `HIGH` etc.), os endereços e os seletores CSS existentes foram preservados. Por exemplo, o JSON ainda retorna `name`, enquanto o código acessa `usuario.nome`.
- Os formulários de conta aceitam tanto `nome`, `perfil`, `senha` quanto as entradas antigas `name`, `role`, `password`.
- As migrations antigas permanecem intactas. O alias `UsuarioManager` existe exclusivamente para carregar o histórico de migrations.

## Banco e atualização

A migration `0005_identificadores_portugues` renomeia seis campos da conta e ajusta a restrição que impede reativar contas excluídas. Ela preserva identificadores, datas, senhas protegidas e vínculos com os chamados. Execute `manage.py migrate` ao atualizar outra instalação.

Exporte backups JSON depois de aplicar a atualização: as novas exportações usam os nomes em português. Para restaurar um JSON anterior, use primeiro a versão anterior do projeto, carregue esse backup em um banco separado e então atualize o código e execute a migration. Não renomeie campos de backups manualmente.
