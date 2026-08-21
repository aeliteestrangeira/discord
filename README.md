# Discord — aplicação web direta

[Aplicação](https://aeliteestrangeira.github.io/discord/) · [CI](https://github.com/aeliteestrangeira/discord/actions/workflows/ci.yml) · [Deploy do Pages](https://github.com/aeliteestrangeira/discord/actions/workflows/pages.yml)

Este repositório contém a aplicação web publicada diretamente pelo GitHub Pages e as fontes controladas do backend remoto Supabase. Não existe landing page, servidor local, administração local ou dependência de um computador do proprietário para manter a aplicação disponível.

## Julgamento principal

**Avaliação:** é quase certo que o GitHub Pages e o Supabase remoto constituem a arquitetura operacional atual. **Probabilidade estimada:** superior a 95%. **Confiança analítica:** alta, baseada no artefato publicado, nos workflows ativos, nas chamadas do frontend e no inventário das Edge Functions implantadas.

O Electron não integra esta versão do repositório. Quando retomado, deverá consumir as mesmas fontes canônicas de HTML, CSS e JavaScript, produzir release próprio e permanecer independente da URL do GitHub Pages.

## Arquitetura vigente

```text
             FONTES CANÔNICAS CONGELADAS
                    HTML + CSS + JS
                           │
                           ▼
                 GitHub Pages direto
                    sem landing page
                           │ HTTPS
               ┌───────────┴───────────┐
               ▼                       ▼
        Supabase remoto             Cloudinary
     Auth · Postgres · Edge       ativos visuais públicos
```

### Fatos observados

- `main` produz o site por `.github/workflows/pages.yml`.
- `priv/static/pages/` e `assets/css/` contêm as capturas canônicas protegidas.
- `assets/js/` contém o runtime web que conecta a aplicação ao Supabase.
- `assets/pages-images/` contém 150 fallbacks usados pelas capturas canônicas.
- `supabase/functions/` contém as três Edge Functions encontradas em produção.
- `supabase/migrations/000_current_schema.sql` consolida o estado SQL controlado.
- Os releases `v4.3.7` e `v4.3.6` permanecem como registros históricos. Eles não são o runtime do Pages.

### Limites da conclusão

- O estado do GitHub e do Supabase pode mudar depois da última evidência registrada.
- `supabase/DEPLOYED_STATE.json` é uma fotografia de governança, não um mecanismo automático de sincronização.
- Os artefatos históricos dos dois releases não devem ser interpretados como aprovação do Electron para uso atual.

## Fontes e responsabilidades

```text
assets/
  css/                    CSS canônico e congelado
  js/                     runtime web e integração cloud
  pages-images/           fallbacks visuais referenciados
priv/
  scripts/build_pages.py  builder determinístico do Pages
  static/pages/           HTML canônico e congelado
  static/fonts/           fontes referenciadas
  static/assets/          SVGs auxiliares referenciados
supabase/
  config.toml             política de JWT das Edge Functions
  functions/              fontes implantadas no backend remoto
  migrations/             snapshot SQL consolidado
test/
  test_pages_publish.py   controles de regressão e escopo
```

Qualquer arquivo fora dessas responsabilidades deve ser tratado como candidato a resíduo e precisa de evidência de uso antes de ser incorporado.

## Build e validação

O builder usa apenas a biblioteca padrão do Python. Ele altera somente a cópia gerada; as fontes congeladas não são reescritas.

```powershell
python -m unittest discover -s test -p "test_*.py" -v
python priv/scripts/build_pages.py --output _site
```

O artefato `_site/` inclui:

- aplicação direta em `index.html`;
- rotas de login, cadastro, canais, guilda e administração web;
- runtime JavaScript versionado por digest;
- `BUILD_INFO.json` com hashes das fontes congeladas;
- `PAGES_SHA256.txt` com hashes de todos os arquivos publicados.

O CI também executa verificação sintática de todos os arquivos JavaScript. Uma alteração não deve ser promovida quando qualquer teste, hash, referência de imagem ou build falhar.

## Backend remoto

O projeto Supabase de produção é `kwekrdluscriubyfolri`.

| Função | Finalidade | Verificação JWT |
|---|---|---:|
| `public-config` | Entrega configuração pública restrita à origem autorizada | Não |
| `username-availability` | Retorna apenas disponibilidade de um nome validado | Não |
| `admin-gate` | Autoriza o administrador e exige AAL2 antes de dados administrativos | Sim |

As duas funções públicas existem para bootstrap e cadastro anônimo. Elas não recebem `service_role` do navegador. Segredos e operações privilegiadas permanecem no ambiente das Edge Functions.

O snapshot SQL exige RLS nas tabelas expostas, restringe perfis ao próprio usuário e mantém a autorização administrativa em função controlada. Mudanças de schema devem ser revisadas separadamente do frontend e validadas no Supabase antes da promoção.

## Fronteiras de segurança

- A chave presente no navegador é publicável, nunca `service_role` ou chave secreta.
- Autorização não pode depender de `user_metadata` controlável pelo usuário.
- O hCaptcha é um controle remoto; a site key é pública e o segredo permanece no backend.
- O painel web depende de sessão válida, autorização administrativa e MFA AAL2.
- GitHub Pages não executa endpoints `/api`, Python, Flask, PowerShell ou administração local.
- Cloudinary hospeda ativos públicos; credenciais de gestão não pertencem ao frontend.
- Dados de produção, tokens, senhas, cookies e chaves privadas não devem ser commitados.

## Situação decisória

| Tema | Avaliação | Confiança | Decisão vigente |
|---|---|---:|---|
| Disponibilidade web | Muito provavelmente independente de máquina local | Alta | Operar por Pages + Supabase |
| Fontes canônicas | Quase certamente preservadas pelo build e pelos hashes | Alta | Alterar somente por mudança aprovada |
| Electron | Não faz parte do runtime vigente | Alta | Reconstruir em fase posterior |
| Releases | Exatamente dois registros históricos visíveis | Alta | Não publicar novos até a fase Electron |
| Cloudinary automatizado | Credenciais de automação provavelmente exigem rotação | Média | Validar antes do próximo lote |

### Vocabulário estimativo

Para reduzir ambiguidade, este projeto usa as seguintes faixas inspiradas na tradição analítica de Sherman Kent:

| Expressão | Probabilidade |
|---|---:|
| Quase certamente | acima de 95% |
| Muito provável | 80–95% |
| Provável | 55–80% |
| Equilíbrio de possibilidades | 45–55% |
| Improvável | 20–45% |
| Muito improvável | 5–20% |
| Quase certamente não | abaixo de 5% |

Probabilidade e confiança são registradas separadamente: probabilidade expressa a chance estimada da conclusão; confiança expressa qualidade, consistência e suficiência das evidências.

## Governança de mudanças

1. Declarar impacto empresarial, controle afetado e hipótese da mudança.
2. Alterar a menor superfície possível sem editar silenciosamente as fontes congeladas.
3. Executar testes, build, verificação de hashes e revisão de referências.
4. Publicar por branch e pull request; não alterar `main` diretamente.
5. Exigir CI e deploy concluídos antes da validação de produção.
6. Registrar evidência de eficácia e risco residual.

### Critério para retomar o Electron

O Electron somente deve retornar quando houver decisão explícita sobre empacotamento, atualização, assinatura, persistência, segregação de segredos e teste independente. A implementação futura não deverá usar o GitHub Pages como `loadURL` e não deverá reintroduzir Flask, painel local ou credenciais administrativas locais sem nova aceitação formal de risco.
