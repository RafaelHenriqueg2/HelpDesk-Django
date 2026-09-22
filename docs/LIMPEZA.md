# Revisão de limpeza — 22/09/2026

Base: commit `98d319cded34771e744f6d8fd40e6f5a750de351` do repositório HelpDesk-Django.

## Removido

- 16 imports sem uso em código e testes.
- `fluxo.marcar_lidas`: função sem chamadas. A leitura de notificações continua nas views e na API; a view de detalhes preserva seu filtro por instante de corte.
- `FormularioChamado.clean_anexo`: apenas devolvia o resultado já produzido pelo campo. A validação de conteúdo, quantidade e tamanho permanece no campo e no fluxo de gravação.
- 164 seletores CSS sem uso nos templates e código atuais, incluindo `#__next` e componentes do frontend antigo. `style.css` passou de 1.985 para 1.198 linhas. Status e urgência dinâmicos, mensagens de erro Django, tema escuro e regras responsivas utilizadas foram mantidos.
- `parar.cmd`: somente mostrava uma instrução; não encerrava o servidor. Use Ctrl+C na janela aberta por `iniciar.cmd`, como já descrito no README.

## Por que os requirements continuam

Não foi identificada uma dependência direta removível sem retirar suporte configurado. Os arquivos foram mantidos, com comentários nas listas principais.

| Dependência | Uso no projeto |
| --- | --- |
| Django | Portal, ORM, sessões, administração, migrations e testes |
| djangorestframework | API REST e seus testes |
| PyJWT | Emissão e verificação dos tokens da API |
| python-dotenv | Carrega `.env` ou o arquivo indicado por `HELPDESK_ENV_FILE` |
| dj-database-url | Interpreta `DATABASE_URL` em `settings.py` |
| psycopg[binary] | Driver PostgreSQL, necessário para o Supabase |
| Pillow | Confere conteúdo e formato das imagens anexadas |
| bcrypt | Backend `BCryptPasswordHasher` configurado; mantido para compatibilidade com senhas existentes, cujo banco remoto não foi inspecionado |
| django-storages[s3] | Backend dos anexos privados no Supabase Storage |

`requirements.txt` contém as dependências comuns; `requirements-cloud.txt` inclui essa lista e adiciona o armazenamento S3. Os dois arquivos `*-lock.txt` registram versões exatas, inclusive dependências indiretas. Eles permitem reproduzir ambientes e não são pacotes adicionais executados junto com a aplicação. As versões existentes foram preservadas.

Para a instalação com Supabase Storage, use `pip install -r requirements-cloud.txt`; para reproduzir as versões da validação desta revisão, use `pip install -r requirements-cloud-lock.txt`.

## Por que os testes continuam

Os quatro arquivos contêm 73 testes de funcionalidades reais, não exemplos aleatórios. Eles cobrem permissões, autenticação, anexos, atendimento, transferência de dados e preservação de contas durante migrations. São executados com `manage.py test chamados`, não durante o uso normal do portal. O próprio Django fornece a infraestrutura de testes.

## Integração e dados preservados

Foram mantidos os modelos, todas as migrations, API, configuração PostgreSQL/S3, arquivos de exemplo de ambiente e comandos de exportação, importação, cópia de anexos e preparação do banco compartilhado. Também foram mantidos os pontos de entrada WSGI/ASGI e arquivos `__init__.py`, usados pelo Python e Django.

Nenhuma credencial, banco real ou anexo do grupo foi acessado. A integração real com Supabase deve ser conferida ao configurar esta máquina; esta limpeza foi testada em SQLite isolado e com o backend S3 sem rede. Os testes passaram, mas não substituem essa verificação da conexão real.
