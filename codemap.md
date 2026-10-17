# DadosJah_StatusDFe/

## Responsibility
Monitor web de status dos servicos SEFAZ (DF-e). Consome a API DadosJah, armazena o historico em SQLite e exibe um dashboard com a grade UF x documento.

## Design
- **Raiz do projeto:** `AGENTS.md` (regras de IA), `codemap.md` (este mapa), `.gitignore`, `.env.example`, `requirements.txt` (pins exatos), `criar-venv.bat` / `entrar-venv.bat`.
- **Processo unico** (Python 3.12): Flask + APScheduler + SQLite + Jinja2 no mesmo processo, para economia de RAM na VPS.
- **Sem build tools:** frontend em HTML + CSS puro + JS vanilla.

## Flow
1. APScheduler dispara a coleta a cada `INTERVALO_COLETA_MIN` (padrao 5 min).
2. O coletor consulta a API DadosJah por UF x documento x ambiente e classifica o `cStat`.
3. Cada leitura e gravada na tabela `leituras` do SQLite (WAL).
4. Flask le o banco e serve o dashboard; o browser faz polling em `/api/status` (60 s).
5. Job diario aplica a retencao de `RETENCAO_DIAS` dias.

## Integration
- **API DadosJah:** `https://api-dfe.dadosjah.com.br/v1/nfe/service-status` (configuravel via `API_BASE_URL`).
- **Configuracao:** `.env` na raiz (copiado de `.env.example`); nunca versionado.
- **Saidas de runtime:** `logs/` (log diario) e `data/` (banco SQLite) — ambos fora do controle de versao.

# src/

## Responsibility
Codigo-fonte da aplicacao Python: configuracao, utilitarios, agendador, regras de negocio e interface web Flask.

## Design
- **Nomenclatura hibrida:** infraestrutura em EN (`settings`, `logger`, `db`), dominio em PT-BR (`coletar`, `classificar`).
- **Bootstrap:** scripts executaveis inserem a raiz do projeto no `sys.path` via `Path(__file__).resolve().parents[2]`.
- **Codigo ASCII puro** (sem acentos) e imports absolutos `from src.utils...`.
- **Milestones:** `jobs/`, `services/` e `app.py` (apenas `/health`) existem desde o M1; `web/` (dashboard) pertence ao M3.

## Subpastas
| Pasta | Conteudo | Status |
|---|---|---|
| `utils/` | Utilitarios compartilhados (`settings.py`, `logger.py`, `db.py`, `config.py`, `segredos.py`) | Ativo |
| `jobs/` | Coleta periodica + retencao (APScheduler) | Ativo (M1) |
| `services/` | Regras de negocio (classificacao, cliente da API, auth) | Ativo (M1–M2) |
| `scripts/` | `configurar.py` — primeiro boot (master key + senha admin) | Ativo (M2) |
| `web/` | Templates (`index`, `detalhe`, `config`), estaticos (css/js/logos) | Ativo (M2–M3) |
| `app.py` | `/health` (M1), `/config` (M2), dashboard + APIs (M3) | Ativo (M1–M3) |

## Flow
1. `app.py` importa `utils.settings` e carrega o `.env`.
2. `utils.db` garante o schema no banco SQLite.
3. Jobs, services e web compartilham os mesmos utilitarios.

## Integration
- Consome a API DadosJah via `httpx` (jobs).
- Persiste em SQLite via `utils/db.py`.
- Serve HTML/CSS/JS via Flask + Jinja2 (`web/`).

# src/utils/

## Responsibility
Utilitarios transversais: configuracao, logging e acesso ao banco de dados.

## Design
- `settings.py` — classe `Settings` (defaults sem segredos) + `carregar_env()` (python-dotenv, `override=False`); propriedades `lista_ufs`, `lista_documentos`, `lista_tp_ambs`.
- `logger.py` — `configurar_logger(nome_modulo)`: configura o logger raiz uma unica vez (arquivo diario `logs/<modulo>_<AAAA-MM-DD>.log` + console), fuso America/Sao_Paulo (ZoneInfo), formato `%(asctime)s %(levelname)s %(name)s %(message)s`.
- `db.py` — `caminho_banco()`, context manager `conexao()` (sqlite3, `Row`, `foreign_keys` on) e `criar_schema(conn)` (tabelas `leituras`, `modelos_dfe`, `configuracoes`, indice, seeds idempotentes e `PRAGMA journal_mode=WAL`).
- `config.py` — `buscar_configuracao`/`definir_configuracao` (tabela `configuracoes`) e helpers tipados que releem o banco a cada chamada: `ufs_monitoradas`, `modelos_ativos`, `modelos_ativos_dfe`, `intervalo_min`, `timeout_s`, `retencao_dados_dias`, `retencao_logs_dias`.
- `segredos.py` — `cifrar`/`decifrar` (Fernet: AES-128-CBC + HMAC-SHA256), `gravar_segredo`/`buscar_segredo` (tabela `segredos`, master key via env), `hash_senha`/`verificar_senha` (PBKDF2-HMAC-SHA256 600k, `compare_digest`).

## Flow
1. `settings.carregar_env()` popula `Settings` a partir do `.env`.
2. `logger.configurar_logger()` prepara o logging (arquivo + console).
3. `db.criar_schema()` cria/garante a estrutura do banco.

## Integration
- Base comum importada por jobs, services e app Flask.
- Caminho do banco derivado de `Settings.BANCO_CAMINHO` (relativo a raiz).
- Logs gravados em `logs/`; banco em `data/`.

# src/services/

## Responsibility
Regras de negocio: classificacao de status e cliente HTTP da API DadosJah.

## Design
- `classificar.py` — constantes de estado/cor (design system) e `classificar(cstat, erro)` -> dict `{"estado", "cor"}`. Regras: 107 operacional, 108 instavel, 109 indisponivel; cStat ausente/outro ou `erro` -> sem_dados.
- `api_dadosjah.py` — `consultar_status(uf, endpoint, tp_amb, timeout_s)` via httpx; mede `response_time` em ms (perf_counter); nunca loga segredos; HTTP != 200 e excecoes viram `erro`; normaliza `data.status` -> raiz; Bearer + retry em 401/403.
- `auth_dadosjah.py` — `obter_token(forcar=False)`: login na API (`POST /v1/auth/user/login`) com credenciais do `.env`; token JWT em RAM com cache por expiracao.

## Flow
1. `coletar` chama `api_dadosjah.consultar_status` por UF x modelo x ambiente.
2. `classificar` traduz o cStat para o estado do semaforo (usado pela apresentacao).

## Integration
- Consome `Settings.API_BASE_URL` (src/utils/settings.py).

# src/jobs/

## Responsibility
Tarefas agendadas (APScheduler): coleta periodica e retencao de dados/logs.

## Design
- `coletar.py` — `executar_ciclo()` (sequencial modelos x UFs x ambientes, uma conexao SQLite por ciclo), `agendar(scheduler)` (job de intervalo) com `reschedule_job` quando `intervalo_min` muda no banco (aceite M1: configuracao viva sem restart).
- `reter.py` — `executar_retencao()` (DELETE de leituras antigas + remocao de logs por mtime), `agendar(scheduler)` (diario as 03:00).

## Flow
1. `app.py` cria o `BackgroundScheduler` e chama `coletar.agendar` e `reter.agendar`.
2. Cada ciclo rele as configuracoes do banco (tabela `configuracoes`).

## Integration
- Persiste em SQLite via `src/utils/db.py`; le configuracoes via `src/utils/config.py`; estados via `src/services/classificar.py`.

# src/scripts/

## Responsibility
Scripts de operacao: primeiro boot (master key + senha admin).

## Design
- `configurar.py` — wizard idempotente: gera `MONITOR_MASTER_KEY` e anexa ao `.env` (chmod 600 no Linux), define `admin_senha_hash` (getpass duplo) na tabela `configuracoes`.

## Flow
1. Rodar uma vez no primeiro boot, antes de usar o painel `/config`.

## Integration
- Usa `src/utils/segredos.py` (hash), `src/utils/db.py` (schema) e `src/utils/settings.py` (caminho do `.env`).

# src/web/

## Responsibility
Interface web: templates Jinja2 e estaticos (CSS, JS, logos).

## Design
- `templates/index.html` — dashboard: grade UF x modelo com celulas do semaforo, toggle producao/homologacao, legenda e nota "sem dados" x "indisponivel"; recebe `celulas`, `ufs`, `modelos`, `ambientes`, `gerado_em`.
- `templates/detalhe.html` — detalhe por UF: card de ultimo status, barra de uptime 24 h, sparkline de latencia (SVG), seletores de documento/ambiente.
- `templates/config.html` — painel `/config` (login + filtros), com CSRF e flash messages.
- `static/js/app.js` — JS vanilla: polling de `/api/status` a cada 60 s, toggle de ambiente, sparkline, re-fetch de historico.
- `static/css/style.css` — design system (:root cores dadosjah, componentes, grade, celulas, uptime, sparkline).
- `static/logos/` — 4 logos DadosJah (favicon, navbar, footer).

## Flow
1. Flask renderiza os templates com o estado inicial do banco.
2. O browser faz polling nas APIs JSON e atualiza as celulas sem recarregar.

## Integration
- Consome as rotas de `src/app.py` (`/`, `/uf/<uf>`, `/api/status`, `/api/uf/<uf>/historico`) e os estados/cores de `src/services/classificar.py`.

# docs/

## Responsibility
Documentacao do projeto em Portugues do Brasil (UTF-8 sem BOM).

## Design
- `implementation_plan.md` — plano do projeto com milestones M0–M5.
- `especificacao.md` — contrato normativo (contexto, principios, requisitos, arquitetura, modelo de dados, classificacao, rotas, restricoes).
- `panorama-atual.md` — status vivo, atualizado a cada mudanca relevante.
- `explicacao-codigo.md` — explicacao didatica do codigo (Python x Delphi); criado em milestone futuro.

## Flow
1. Ler `especificacao.md` antes de implementar.
2. Atualizar `panorama-atual.md` no mesmo commit da mudanca.
3. Atualizar `explicacao-codigo.md` a cada alteracao relevante de codigo.

## Integration
- Referenciados pelo `AGENTS.md`.
- Documentos de topo de qualquer milestone.
