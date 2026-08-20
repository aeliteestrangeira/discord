# Discord Flask + Supabase — baseline atual

Aplicação Flask com autenticação Supabase, hCaptcha, administração local e preparação de mídia no Cloudinary.

## Regra de baseline imutável

Os HTML e CSS fornecidos são artefatos congelados. Correções de comportamento, segurança, integração e migração são implementadas em JavaScript/Python/SQL sem reescrever o markup ou o stylesheet capturado. A suíte de regressão valida SHA-256 dos HTML/CSS protegidos.

Arquivos protegidos incluem as páginas públicas/autenticadas, templates administrativos e os CSS correspondentes. Se uma alteração exigir novo comportamento visual, o código deve consumir a estrutura/classes existentes; não deve modificar os arquivos protegidos.

## Configuração privada

A aplicação aceita bootstrap privado por `config/SUPABASE_PRIVILEGED.env` e persiste os valores no armazenamento criptografado `instance/control.sqlite3`, protegido por chaves geradas localmente em `instance/`. O bootstrap copia valores ausentes sem apagar nem reescrever o arquivo de origem. Valores já existentes no armazenamento criptografado prevalecem.

**Limite público da distribuição:** `config/SUPABASE_PRIVILEGED.env` não faz parte do repositório público, do GitHub Pages, das GitHub Releases nem do instalador distribuído a clientes. No ambiente do proprietário/desenvolvimento, o bootstrap privado pode ser importado explicitamente para a árvore persistente e permanece fora do artefato público. O distribuível também não carrega `instance/control.sqlite3`, `master.key`, `csrf.key`, `audit.key`, sessões ou estado de runtime; essas chaves e estados são criados ou preservados localmente.

Variáveis suportadas:

- Supabase: `SUPABASE_URL`, `SUPABASE_PROJECT_REF`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `SUPABASE_LEGACY_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_LEGACY_SECRET`, `SUPABASE_JWKS_URL`, `SUPABASE_JWKS_KID`, `SUPABASE_JWKS_PREVIOUS_KID`, `SUPABASE_JWKS_STATIC_JSON`, `SUPABASE_DB_HOST`, `SUPABASE_DB_PASSWORD`.
- hCaptcha: `HCAPTCHA_SITE_KEY`, `HCAPTCHA_SECRET`.
- Cloudinary: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `CLOUDINARY_FOLDER`.
- Gmail API, ainda opcional/não configurado: remetente, OAuth Client ID, Client Secret e refresh token.

O artefato público contém somente configuração não secreta necessária ao cliente. Valores privilegiados ausentes continuam fail-closed até serem fornecidos no ambiente privado apropriado. Credenciais Google permanecem opcionais.

Segredos nunca devem ser enviados ao navegador, registrados em logs ou adicionados ao manifesto público de integridade.

## Supabase e banco

O cliente público usa somente URL e chave publicável. Operações administrativas exigem a autoridade server-side configurada. O conjunto legado pode ser validado localmente contra o legacy JWT secret, e o JWKS estático pode ser conferido contra o `kid` configurado.

A estrutura SQL atual é deliberadamente consolidada em um único snapshot idempotente:

`priv/supabase/migrations/000_current_schema.sql`

O runner mantém `app_private.schema_migrations`, compara o SHA-256 do snapshot e reaplica o estado desejado para reparar drift quando a conexão PostgreSQL estiver disponível. Não há arquivos SQL históricos paralelos.

## hCaptcha

O frontend recebe somente a sitekey. A verificação é executada server-side em `/api/auth/login` e `/api/auth/register`; ausência, erro de transporte ou `success=false` devolvido pelo `siteverify` resultam em negação. O secret permanece apenas no backend/armazenamento protegido. A partir da 4.3.4, o cliente usa hCaptcha em modo invisível/programático: uma intenção de login dispara `execute()` e erros transitórios `challenge-error`/`internal-error` recebem no máximo uma repetição automática, sem transformar o fluxo em um segundo clique no checkbox. O `hostname` retornado pelo provedor é mantido para auditoria/diagnóstico, mas não transforma localmente um `success=true` em falso negativo. A aplicação protege a origem separadamente por `Host` default-deny e usa apenas `APP_HOSTNAME=discord`. Se a sitekey tiver restrição de domínio habilitada no próprio hCaptcha, o domínio correspondente também precisa aceitar `discord`.

## DOM e JavaScript

O frontend não utiliza `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval()` nem `new Function`.

Construção de DOM dinâmico é centralizada em `assets/js/ui/dom.js`, que usa APIs nativas (`DOMParser`, `DocumentFragment`, `createElement`, `replaceChildren`) e rejeita elementos/atributos perigosos antes de inserir uma árvore. O módulo mantém um único `DOMParser` reutilizado.

Os módulos de UI usam autoridades compartilhadas para estado, overlays e catálogo de menus em vez de criar implementações concorrentes. Novos módulos devem reutilizar essas autoridades antes de adicionar listeners, parsers, overlays ou catálogos próprios.

O carregamento JavaScript é orientado por rota e componente. A página de login não baixa os módulos exclusivos de cadastro (`date-menu.js`, `menu-catalog.js`, `sliding-highlight.js`, `register-validation.js`, `register-form.js`). O módulo de hCaptcha é carregado apenas quando uma ação realmente solicita um desafio. No shell autenticado, criação/entrada em servidor e WebRTC/voz permanecem atrás de imports dinâmicos disparados pela primeira interação correspondente.

## Cloudinary e imagens

O pacote principal não carrega a antiga pasta local `images/`. A rota `/images/<arquivo>` mantém compatibilidade: serve um arquivo local quando existir e, na ausência, resolve a URL de entrega do Cloudinary.

A configuração Cloudinary fica exclusivamente no backend e no armazenamento criptografado. Endpoints administrativos disponíveis:

- `GET /admin/cloudinary/status`
- `POST /admin/cloudinary/config`
- `POST /admin/cloudinary/test`
- `POST /admin/cloudinary/migrate-images` — exige CSRF e confirmação explícita `MIGRAR`.

A migração usa nomes públicos determinísticos sob a pasta configurada para preservar referências existentes. A captura possui uma referência histórica `0085-og_img_discord_home.png`; o backend mantém alias para o ativo fornecido `0084-og_img_discord_home.png` sem alterar HTML/CSS.

A cópia das imagens de origem para uma migração inicial deve ser mantida fora do pacote principal. Para migrar, extraia os arquivos em `instance/cloudinary-import/`; o endpoint administrativo informa quantos arquivos estão prontos e usa esse staging privado como fonte. O caminho legado `images/` é apenas fallback de compatibilidade.

## Administração

O plano de controle é operado por um único administrador do proprietário. O provisionamento/reset administrativo não é distribuído no repositório público nem no instalador de clientes; manutenção do proprietário usa ferramenta privada externa, mantida fora do GitHub. Após autenticação administrativa local:

- `/admin` — estado do serviço e auditoria;
- `/admin/config` — configuração efetiva/mascarada dos provedores;
- `/admin/users` — usuários Supabase, quando a autoridade administrativa estiver configurada;
- `/admin/tables` — catálogo/migração PostgreSQL quando a conexão direta estiver configurada;
- `/admin/audit` — cadeia HMAC de auditoria;
- endpoints `/admin/cloudinary/*` — estado, teste, configuração e migração de mídia.

Segredos são exibidos apenas de forma mascarada. Campos de substituição vazios não significam que a credencial armazenada foi removida.

## Autenticação e senhas

- login por senha não pré-consulta a existência do e-mail e devolve resposta pública uniforme para conta inexistente ou senha inválida;
- recuperação de conta usa resposta genérica (`Se a conta existir...`) para não expor existência de identidade;
- cadastro e redefinição administrativa exigem senha de pelo menos 16 caracteres, diversidade mínima e rejeitam senhas triviais/contendo o identificador;
- administradores locais continuam bloqueados após repetidas falhas e, quando `ADMIN_LOCAL_ONLY=1`, não autenticam fora de loopback;
- `Host` é validado por allowlist singular (`APP_HOSTNAME=discord`) para bloquear DNS rebinding/Host-header abuse contra o servidor local;
- ao iniciar/instalar, o script de hardening restringe ACL de `instance/`, `.env` e `config/SUPABASE_PRIVILEGED.env` ao usuário atual e LocalSystem.

## SPA e desempenho do shell autenticado

- o shell `/channels/*` não usa mais heartbeat/polling periódico de sessão; remoção local de cookie usa Cookie Store/BroadcastChannel quando disponíveis e validação remota ocorre por eventos reais (`focus`, `pageshow`, `online`, `visibilitychange`) ou por requisições protegidas;
- pedidos de amizade não fazem refresh periódico: o estado inicial é hidratado server-side e atualizações ocorrem por mutações/foco/visibilidade;
- a partir da 4.3.4, transições entre Home, servidores e canais usam navegação documental completa por `location.assign()`, garantindo que toolbar, lista de membros, controladores de rota e DOM sejam hidratados pelo mesmo documento;
- a antiga substituição parcial com `DOMParser`/`fetch`/History API permanece desabilitada até existir lifecycle explícito `mount/unmount/rehydrate` para todos os componentes persistentes do shell;
- a otimização de consulta do backend permanece válida: cada documento de guild ainda resolve servidor + canais com o caminho PostgreSQL consolidado.

O polling de `assets/js/ui/voice.js` é separado: ele só existe depois que uma sessão de voz é efetivamente conectada e não participa da validação da sessão web.

## Default deny

- autenticação sem hCaptcha válido: negada;
- operação Supabase privilegiada sem chave administrativa: negada;
- operação PostgreSQL sem senha/conexão completa: negada;
- POST administrativo sem CSRF: negado;
- acesso `/admin/*` fora da política local/sessão administrativa: negado;
- conteúdo dinâmico não confiável em árvore DOM: rejeitado pelo helper central;
- caminhos de arquivos e módulos: allowlist onde aplicável.

## Arquitetura ativa

Somente artefatos de arquitetura ainda executáveis/úteis permanecem:

- `priv/architecture/app-flow.yaml`
- `priv/architecture/channels-baseline.json`
- `priv/architecture/state-model.json`

Documentação histórica, manifests de fontes/cursos e relatórios antigos foram removidos. Este `README.md` é o único arquivo Markdown mantido como referência operacional e de regressão.

## Verificação

Antes de promover uma versão:

```text
python -m unittest discover -s test -v
python verify_architecture.py
python verify_integrity.py
node --check <cada arquivo .js>
```

Também confirme:

1. SHA-256 de todos os HTML/CSS protegidos permanece igual ao baseline;
2. busca por sinks HTML perigosos em JavaScript retorna zero;
3. existe exatamente um `.sql`, em `priv/supabase/migrations/`;
4. existe somente `README.md` como Markdown;
5. `config/SUPABASE_PRIVILEGED.env`, `instance/`, `.runtime/`, caches e segredos não fazem parte do repositório/release/manifesto público; bootstrap privado do proprietário é persistido somente fora do artefato distribuído;
6. testes externos de Supabase/PostgreSQL/hCaptcha/Cloudinary são executados apenas em ambiente com rede e credenciais completas.

## Dependências e atualizações

`INSTALL_DEPENDENCIES.bat` valida o ambiente com `pip check` e preserva em `instance/requirements.resolved.txt` o conjunto exato resolvido na primeira instalação. Atualizações seguintes usam esse snapshot como constraint, reduzindo drift silencioso entre versões; se uma atualização exigir dependências incompatíveis com o snapshot, a instalação falha em vez de substituir versões implicitamente.

## Instalação local

1. `INSTALL_DEPENDENCIES.bat` para desenvolvimento/source;
2. forneça configuração privilegiada somente por bootstrap privado externo quando estiver operando o ambiente do proprietário;
3. configure a senha PostgreSQL no plano de controle privado antes de operações de schema;
4. `SERVER.bat`;
5. use `PRECHECK.bat` antes da promoção.

Clientes do Electron usam o instalador publicado e não criam administradores locais. Provisionamento ou reset do único administrador do proprietário é uma operação de manutenção privada e não possui BAT/Python público no repositório. Em atualizações, preserve a árvore persistente local. Em instalação pública nova, nenhum bootstrap privilegiado é distribuído com o artefato; `instance/` é criado no primeiro uso para evitar distribuir chaves, sessões e banco local de outra instalação.


## Layout Elixir/Phoenix adotado

A árvore de código foi reorganizada para usar os mesmos diretórios de primeiro nível de uma aplicação Phoenix: `assets/`, `config/`, `lib/`, `priv/` e `test/`. O runtime continua Python/Flask; esta mudança é de arquitetura física e separação de responsabilidades, não uma alegação de conversão para Elixir.

```text
assets/
  css/                  # folhas de estilo de origem
  js/
    ui/                  # módulos SPA/voz/browser
config/                  # bootstrap/configuração de deployment
lib/
  discord_app/           # domínio, segurança, storage, provedores
  discord_app_web/
    app.py               # composição Flask; sem regras de negócio/rotas
    router.py            # registro central dos módulos de rota
    runtime.py           # serviços e configuração de runtime
    security.py          # sessão, CSRF, Host allowlist e headers
    registration.py      # prontidão/validação do schema
    presenters.py        # projeções HTML server-side do shell
    controllers/
      auth/              # login, passkey, cadastro e sessão
      admin/             # configuração, usuários, banco e auditoria
      guilds.py          # guilds/canais
      friends.py         # amizades
      voice.py           # voz/sinalização
      assets.py          # assets públicos allowlisted
      pages.py           # páginas públicas
    templates/admin/     # templates do plano de controle
priv/
  architecture/          # modelos/artefatos operacionais
  scripts/               # utilitários de instalação/runtime
  static/                # páginas e assets públicos congelados
  supabase/migrations/   # snapshot SQL externo; não existe Ecto Repo
test/                    # regressão e segurança
```

Não existem `core/`, `frontend/`, `fonts/`, `templates/`, `tests/`, `architecture/`, `supabase/` ou `scripts/` soltos na raiz. `app.py` na raiz é somente um launcher de compatibilidade. `lib/discord_app_web/app.py` agora é apenas o composition root (cerca de 2 KB); rotas e comportamento ficam nos controllers especializados, evitando o antigo monólito de aproximadamente 140 KB.

## Sons dos controles de voz

Os quatro efeitos de mute/unmute ficam centralizados em `assets/js/ui/voice-sounds.js`. Os MP3 não são pré-carregados no shell ocioso; o soundboard é preparado apenas depois que a sessão de voz conecta. O estado lógico não depende do HTML/ícone: `VoiceRuntime.setMicrophoneMuted()` e `VoiceRuntime.setHeadphonesMuted()` executam o áudio e depois sincronizam qualquer controle visual disponível. A aplicação também aceita o evento `app:voice-control`, preparado para futuros botões/HTML.

Ações aceitas em `detail.action`: `mute-microphone`, `unmute-microphone`, `toggle-microphone`, `mute-headphone`, `unmute-headphone`, `toggle-headphone`. O CSP inclui `media-src https://res.cloudinary.com` exclusivamente para permitir esses efeitos de áudio do Cloudinary.

## Aplicativo desktop Electron — fase 1

A partir da versão desktop alpha, `DESKTOP_START.bat` abre **a mesma aplicação Flask** dentro de Electron. O shell desktop não reimplementa a interface: ele prepara o hostname/TLS local, inicia o backend existente em `127.0.0.1:8000`, confirma `/api/desktop/health` e carrega `https://discord:8000/` em uma `BrowserWindow` isolada.

O renderer Electron opera com Node desabilitado, isolamento de contexto, sandbox, `webSecurity`, bloqueio de novas janelas e política de permissões em default-deny. Apenas acesso ao microfone é permitido para a origem local da aplicação, necessário para o recurso de voz. O certificado local nunca é aceito por bypass; a confiança precisa ser instalada corretamente pelo fluxo TLS já existente.

Esta fase ainda é de desenvolvimento desktop. O instalador público/auto-update por GitHub Releases será adicionado depois que o runtime Python e o diretório persistente `instance/` forem separados do diretório de aplicação.

## Desktop 4.2.2: correcoes de build e integridade multiplataforma

A versao 4.2.2 corrige o empacotamento PyInstaller no GitHub Actions usando caminhos absolutos para todos os `--add-data`, evitando que `--specpath` rebata caminhos relativos para `build/pyinstaller-spec/`. O manifesto `HASHES.sha256` e o verificador agora canonizam finais de linha conforme a politica do repositorio, mantendo verificacao deterministica em clones Linux e Windows sem enfraquecer os hashes de conteudo.

## Desktop 4.2.3: runtime Windows PowerShell

A versao 4.2.3 corrige a inicializacao do instalador em maquinas nas quais `powershell.exe` nao esta resolvivel pelo `PATH` herdado pelo Electron. O desktop empacotado agora resolve o Windows PowerShell por caminho absoluto confiavel em `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`, com fallback controlado para PowerShell 7 em `%ProgramFiles%\PowerShell\7\pwsh.exe`. O fluxo de elevacao do hostname reutiliza o proprio executavel PowerShell ja em execucao, evitando uma segunda resolucao via `PATH`. Ferramentas do sistema usadas no bootstrap (`cmd.exe`, `icacls.exe` e `ipconfig.exe`) tambem sao resolvidas por caminhos do Windows quando aplicavel.

Esta mudanca evita tanto falhas `spawn powershell.exe ENOENT` quanto dependencia desnecessaria de caminhos pesquisaveis controlados pelo usuario.

## Desktop 4.2.4: working directory do runtime empacotado

A versao 4.2.4 corrige uma segunda causa de `ENOENT` observada apenas no aplicativo instalado. O executavel do PowerShell ja era resolvido por caminho absoluto e validado como arquivo existente, mas `child_process.spawn()` ainda herdava `SOURCE_ROOT` como `cwd`. Em um Electron empacotado, esse caminho aponta para dentro de `app.asar`, que nao e um diretorio de trabalho valido para `CreateProcess` no Windows. O runtime agora usa `%LOCALAPPDATA%\AEliteEstrangeira\DiscordDesktop` como `cwd` para os scripts PowerShell empacotados, mantem `SOURCE_ROOT` apenas no modo fonte e valida o `cwd` antes de qualquer spawn para produzir erro diagnostico especifico em vez de um `ENOENT` ambiguo.

## Convergência Web/Desktop planejada

Na linha 4.3.x, o GitHub Pages continua sendo o canal público estático de distribuição/documentação. A convergência da aplicação web real com o Electron fica para a linha 5.x: o mesmo frontend versionado será produzido para Web e Desktop, enquanto autenticação, guilds, administração e operações privilegiadas dependerão de backend HTTPS controlado pelo proprietário. GitHub Pages e o Electron público nunca devem receber `service_role`, senha PostgreSQL, segredo hCaptcha, segredo Cloudinary ou credenciais administrativas.

## GitHub Pages e Desktop

A distribuicao publica usa duas superficies separadas derivadas da mesma UI canonica:

- GitHub Pages publica diretamente a tela do aplicativo, sem landing page, por Deploy de `main`.
- Electron continua sendo empacotado e atualizado exclusivamente por GitHub Release/tag; o processo desktop nao usa a URL do Pages como `loadURL`.
- `priv/static/pages/` e `assets/` continuam sendo as fontes canonicas. O builder `priv/scripts/build_pages.py` gera somente o artefato estatico `_site`; os HTML/CSS protegidos nao sao editados.
- GitHub Pages e hospedagem estatica. Endpoints `/api/...` continuam pertencendo ao backend HTTPS de aplicacao e operacoes privilegiadas do Supabase nunca sao publicadas no cliente.

No desktop/WebView, o carregador hCaptcha envia explicitamente o hostname efetivo no parametro publico `host=` do SDK. A verificacao permanece invisivel, programatica e fail-closed; secret hCaptcha continua exclusivamente no backend.
