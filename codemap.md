# DadosJah_StatusDFe/

## Responsibility
Monitor web de status dos serviços SEFAZ (DF-e). Consome APIs de consulta (por padrão a DadosJah), armazena o histórico em SQLite e exibe um dashboard com a grade UF × documento.

## Design
- **Raiz do projeto:** `AGENTS.md` (regras de IA), `codemap.md` (este mapa), `.gitignore`, `.env.example`, `config.example.json`, `Dockerfile`, `requirements.txt` (pins exatos), `criar-venv.bat` / `entrar-venv.bat`, `README.md` (público), `LICENSE` (MIT), `llms.txt`, `robots.txt`, `sitemap.xml` (servidos por rotas Flask), `public/docs/` (documentação pública) e `trash/` (arquivos descartados, não versionados).
- **`config.json`:** configuração operacional na raiz (copiado de `config.example.json`): `coleta`, `retencao`, `web`, `rate_limit` e `links`. Lido uma vez no import (`src/utils/config.py`); alterações exigem restart.
- **`wsgi.py`:** ponto de entrada do gunicorn (caminho avançado). Carrega o `.env`, configura o logger, garante o schema, cria a app (`create_app()`) e inicia o scheduler (`iniciar_scheduler()`) antes de expor `app`. O scheduler roda dentro do processo, então o serviço deve subir com **1 worker** e sem `--preload`.
- **`Dockerfile`:** imagem de execução (`python src/app.py`, porta 5628, volumes para `data/` e `logs/`).
- **Processo único** (Python 3.12): Flask + APScheduler + SQLite + Jinja2 no mesmo processo, para economia de RAM.
- **Sem build tools:** frontend em HTML + CSS puro + JS vanilla.

## Flow
1. O APScheduler dispara a coleta no intervalo de `config.json` (`coleta.intervalo_min`, padrão 5 min).
2. O coletor cria o motor configurado, autentica no início do ciclo e consulta cada UF × documento × ambiente.
3. Cada leitura é gravada na tabela `leituras` do SQLite (WAL).
4. O Flask lê o banco e serve o dashboard; o browser faz polling em `/api/status` (60 s).
5. Job diário aplica a retenção de dados e logs às 03:00 (horário de Brasília), com o corte de datas calculado em Python, e reabre o arquivo de log do dia.

## Integration
- **APIs de consulta:** por padrão `https://api-dfe.dadosjah.com.br` (via `API_BASE_URL`), abstraída pelo pacote `src/motores/`.
- **Configuração:** `.env` (segredos e chaves de boot) + `config.json` (operacional) — nunca versionados os valores reais.
- **Saídas de runtime:** `logs/AAAAMM/` (arquivo por dia em pasta mensal) e `data/` (banco SQLite) — ambos fora do controle de versão.

# src/

## Responsibility
Código-fonte da aplicação Python: configuração, utilitários, agendador, regras de negócio, motores de coleta e interface web Flask.

## Design
- **Nomenclatura híbrida:** infraestrutura em EN (`settings`, `logger`, `db`), domínio em PT-BR (`coletar`, `classificar`, `motores`).
- **Bootstrap:** scripts executáveis inserem a raiz do projeto no `sys.path` via `Path(__file__).resolve().parents[2]` (`src/app.py`, um nível acima, usa `parents[1]`).
- **Código UTF-8 com acentos** (docstrings/comentários em PT-BR; identificadores em ASCII) e imports absolutos `from src.utils...`.
- **Sem interface web de configuração:** a área administrativa foi removida; configurações vêm de `config.json` (deploy).

## Subpastas
| Pasta | Conteúdo | Status |
|---|---|---|
| `utils/` | Utilitários (`settings.py`, `logger.py`, `db.py`, `config.py`, `segredos.py`, `rate_limit.py`, `turnstile.py`) | Ativo |
| `motores/` | Motores de coleta multi-API (`base.py`, `dadosjah.py`, `__init__.py`) | Ativo (Fases 1–2) |
| `jobs/` | Coleta periódica + retenção (APScheduler) | Ativo (M1) |
| `services/` | Regras de negócio (classificação, cliente HTTP, auth) | Ativo (M1–M2) |
| `scripts/` | `configurar.py` — primeiro boot (master key) | Ativo (M2) |
| `web/` | Templates (`index`, `detalhe`, `termos`), estáticos (css/js/logos) | Ativo (M2–M4) |
| `app.py` | Dashboard + APIs JSON, `/health`, `iniciar_scheduler()` | Ativo (M1–M4) |

## Flow
1. `app.py` importa `utils.settings` (`.env`) e `utils.config` (`config.json`).
2. `utils.db` garante o schema no banco SQLite.
3. Jobs, motores, services e web compartilham os mesmos utilitários.

## Integration
- Consome as APIs via `src/motores/` (httpx).
- Persiste em SQLite via `utils/db.py`.
- Serve HTML/CSS/JS via Flask + Jinja2 (`web/`).

# src/utils/

## Responsibility
Utilitários transversais: configuração, logging, banco, criptografia, rate limit e anti-bot.

## Design
- `settings.py` — classe `Settings` (defaults sem segredos) + `carregar_env()` (python-dotenv, `override=False`); propriedades `lista_ufs` e `lista_tp_ambs`. Inclui as chaves `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY`.
- `logger.py` — `configurar_logger(nome_modulo)` configura o logger raiz uma única vez com um `FileHandler` de arquivo por dia em pasta mensal (`logs/AAAAMM/<modulo>_<AAAAMMDD>.log`, fuso America/Sao_Paulo) + console, formato `%(asctime)s %(levelname)s %(name)s %(message)s`. `reabrir_log_do_dia()` fecha/recria o handler do dia (usado pelo job de retenção).
- `db.py` — `caminho_banco()`, context manager `conexao()` (sqlite3, `Row`, `foreign_keys` on) e `criar_schema(conn)` (tabelas `leituras`, `modelos_dfe`, `segredos`, índice, seed de `nfe`, `DROP TABLE IF EXISTS configuracoes` e `PRAGMA journal_mode=WAL`).
- `config.py` — lê `config.json` (`recarregar()` no import) com `_PADROES` embutidos; helpers: `ufs_monitoradas`, `modelos_ativos`, `modelos_ativos_dfe`, `intervalo_min`, `timeout_s`, `retencao_dados_dias`, `retencao_logs_dias`, `motor_ativo`, `porta_web`, `rate_limit_api_min`, `link_github`, `link_ctec`.
- `segredos.py` — `cifrar`/`decifrar` (Fernet: AES-128-CBC + HMAC-SHA256), `gravar_segredo`/`buscar_segredo` (tabela `segredos`, master key via env). Sem hash de senha (não há mais autenticação de admin).
- `rate_limit.py` — classe `RateLimiter` (janela deslizante em memória por chave/IP) usada pelas APIs públicas.
- `turnstile.py` — `turnstile_habilitado()` e `verificar_token(token, ip)` (validação server-side do Cloudflare Turnstile via siteverify; desligado sem chaves).

## Flow
1. `settings.carregar_env()` popula `Settings` a partir do `.env`.
2. `logger.configurar_logger()` prepara o logging (arquivo do dia + console).
3. `config.recarregar()` carrega o `config.json`; `db.criar_schema()` garante o banco.

## Integration
- Base comum importada por motores, jobs, services e app Flask.
- Logs em `logs/AAAAMM/`; banco em `data/`.

# src/motores/

## Responsibility
Camada de abstração multi-API: isolar "de onde vêm os dados de status" por trás de um contrato único, permitindo trocar/adicionar provedores sem mexer no coletor.

## Design
- `base.py` — classe abstrata `MotorBase` (`nome`, `autenticar`, `consultar_status`, `encerrar`): o contrato do motor. O coletor usa `autenticar()` no início do ciclo, `consultar_status(...)` nas consultas e `encerrar(token)` no `finally`.
- `dadosjah.py` — `MotorDadosJah`: implementa o contrato sobre a API DadosJah (`src/services/api_dadosjah.py` + `auth_dadosjah.py`). Renova forçadamente o token no login do ciclo e, em 401/403, refaz o login uma vez; `encerrar()` faz logout e zera a credencial.
- `__init__.py` — registro `_MOTORES` e `criar_motor(nome)`, que devolve uma instância nova do motor solicitado (erro claro se o nome for desconhecido).

## Flow
1. `coletar.executar_ciclo()` lê `config.motor_ativo()` e chama `criar_motor(...)`.
2. `autenticar()` → consultas com o token do ciclo → `encerrar()` no `finally`.

## Integration
- Usa `src/services/` (cliente HTTP e auth) e `src/utils/settings.py`.
- Ponto de extensão: adicionar uma API = criar `src/motores/<api>.py` (subclasse de `MotorBase`) e registrá-la em `_MOTORES`.

# src/services/

## Responsibility
Regras de negócio: classificação de status e cliente HTTP da API DadosJah.

## Design
- `classificar.py` — constantes de estado/cor (design system), `ROTULOS_ESTADO`/`rotulo_estado(estado)` (rótulos exibíveis) e `classificar(cstat, erro)` → dict `{"estado", "cor"}`. Regras: 107 operacional, 108 instável, 109 indisponível; cStat ausente/outro ou `erro` → sem_dados.
- `api_dadosjah.py` — `consultar_status(uf, endpoint, tp_amb, timeout_s, token)` via httpx; mede `response_time` em ms (perf_counter); nunca loga segredos; HTTP != 200 e exceções viram `erro`; normaliza `data.status` → raiz. Recebe o token por parâmetro (a auth é do motor).
- `auth_dadosjah.py` — `obter_token(forcar=False)` (login `POST /v1/auth/user/login`, cache em RAM) e `encerrar_sessao(token)` (logout `POST /v1/auth/user/logout` + limpeza do cache).

## Flow
1. O motor chama `api_dadosjah.consultar_status` por UF × modelo × ambiente.
2. `classificar` traduz o cStat para o estado do semáforo (usado pela apresentação).

## Integration
- Consome `Settings.API_BASE_URL` (src/utils/settings.py).

# src/jobs/

## Responsibility
Tarefas agendadas (APScheduler): coleta periódica e retenção de dados/logs.

## Design
- `coletar.py` — `executar_ciclo()` (cria o motor, autentica, itera modelos × UFs × ambientes com uma conexão SQLite por ciclo, e faz logout no `finally`), `agendar(scheduler)` (job de intervalo) com `reschedule_job` quando `intervalo_min` muda.
- `reter.py` — `executar_retencao()` (DELETE de leituras com corte em Python/ISO UTC + remoção de logs por mtime em `logs/AAAAMM/` e legados, apaga pastas mensais vazias e chama `reabrir_log_do_dia`), `agendar(scheduler)` (job diário `CronTrigger(hour=6)` = 03:00 horário de Brasília, UTC−3).

## Flow
1. `app.py`/`wsgi.py` criam o `BackgroundScheduler` e chamam `coletar.agendar` e `reter.agendar`.
2. Cada ciclo lê a configuração em memória (`config.json`) e o motor configurado.

## Integration
- Persiste em SQLite via `src/utils/db.py`; lê config via `src/utils/config.py`; coleta via `src/motores/`; estados via `src/services/classificar.py`.

# src/scripts/

## Responsibility
Scripts de operação: preparo de primeiro boot.

## Design
- `configurar.py` — script idempotente: gera `MONITOR_MASTER_KEY` e anexa ao `.env` (chmod 600 no Linux) se ainda não existir, e cria/garante o schema do banco. As demais configurações ficam em `config.json` e as credenciais no `.env`.

## Flow
1. Rodar uma vez no primeiro boot (ou quando faltar a master key).

## Integration
- Usa `src/utils/db.py` (schema) e `src/utils/settings.py` (caminho do `.env`).

# src/web/

## Responsibility
Interface web: templates Jinja2 e estáticos (CSS, JS, logos).

## Design
- `templates/index.html` — dashboard: grade UF × modelo com células do semáforo, toggle produção/homologação, legenda e nota "sem dados" × "indisponível"; recebe `celulas`, `ufs`, `modelos`, `ambientes`, `gerado_em`, `turnstile_site_key`. Header com link do GitHub; rodapé com crédito CTEC.
- `templates/detalhe.html` — detalhe por UF: card de último status (com `rotulo`), barra de uptime 24 h, sparkline de latência (SVG), seletores de documento/ambiente. A UF vai no atributo `data-uf` do `<body>` (sem JSON inline).
- `templates/termos.html` — página pública de termos de uso (menciona limite por IP e anti-robô).
- `static/js/app.js` — JS vanilla: polling de `/api/status` a cada 60 s, toggle de ambiente, sparkline e histórico via `fetch`; `_fetchProtegido` injeta o token do Turnstile e renova em 403; `fmtDatetime` usa fuso America/Sao_Paulo.
- `static/css/style.css` — design system (:root cores dadosjah, componentes, grade, células, uptime, sparkline).
- `static/logos/` — 4 logos DadosJah (favicon, navbar, footer).

## Flow
1. Flask renderiza os templates com o estado inicial do banco.
2. O browser faz polling/fetch nas APIs JSON e atualiza as células e o gráfico sem recarregar.

## Integration
- Consome as rotas de `src/app.py` (`/`, `/uf/<uf>`, `/api/status`, `/api/uf/<uf>/historico`) e os estados/cores/rótulos de `src/services/classificar.py`.
- JS externo (nenhum `<script>` inline com dados); a CSP libera scripts apenas de `'self'` e do domínio do Turnstile.

# public/docs/

## Responsibility
Documentação pública do projeto (versionada, faz parte do site e do repositório).

## Design
- `README.md` — índice da documentação pública.
- `uso.md` / `configuracao.md` — uso diário e configuração (`.env` + `config.json`).
- `api.md` — referência das APIs JSON públicas (/api/status, /api/uf/<uf>/historico, /health).
- `arquitetura.md` — componentes, modelo de dados e decisões técnicas.
- `deploy.md` / `como-executar.md` — hospedagem (simples e avançada) e execução local.
- `termos-uso.md` — fonte dos termos de uso (página /termos).

## Flow
1. Documentação nova DEVE ser criada aqui (regra do AGENTS.md).
2. A página `/termos` transcreve `termos-uso.md`.

## Integration
- Referenciada pelo README.md e pelo llms.txt.
- A pasta `docs/` (interna) NÃO é versionada.

# docs/

## Responsibility
Documentação do projeto em Português do Brasil (UTF-8 sem BOM).

## Design
- `implementation_plan.md` — plano do projeto com milestones M0–M5.
- `especificacao.md` — contrato normativo (contexto, princípios, requisitos, arquitetura, modelo de dados, classificação, rotas, restrições).
- `panorama-atual.md` — status vivo, atualizado a cada mudança relevante.
- `explicacao-codigo.md` — explicação didática do código (Python × Delphi); manutenção própria.
- `analise-multiagente.md` — relatório da análise multiagente pré-M5 (achados e correções).

## Flow
1. Ler `especificacao.md` antes de implementar.
2. Atualizar `panorama-atual.md` no mesmo commit da mudança.
3. Atualizar `explicacao-codigo.md` a cada alteração relevante de código.

## Integration
- Referenciados pelo `AGENTS.md`.
- Documentos de topo de qualquer milestone.
