# AGENTS.md — Monitor Status DFe

> Monitor web open-source de status dos serviços SEFAZ (DF-e), alimentado pela API DadosJah.
> Stack: Python 3.12 + Flask + SQLite + APScheduler + Jinja2 + HTML/CSS/JS vanilla.
> Local: raiz do repositório

## Leitura obrigatória (ordem para retomar o projeto em uma nova sessão)

1. `docs/panorama-atual.md` — estado real do projeto (fase atual, decisões, roadmap)
2. `docs/implementation_plan.md` — plano v2 (open-source) com milestones M0–M5 e critérios de aceite
3. `docs/especificacao.md` — contrato normativo (requisitos, arquitetura, modelo de dados)
4. `codemap.md` — mapa do código por pasta

## Comunicação

- Responder sempre em Português do Brasil, de forma clara, objetiva e didática.
- Ao explicar código Python, incluir breve comparação com Delphi quando for útil.

## Workflow

- Antes de alterar código, apresentar um **plano resumido** (o que muda, em quais arquivos, qual abordagem) e aguardar confirmação quando a mudança afetar **3+ arquivos** ou alterar a arquitetura.
- Correções triviais (tipagem, sintaxe, imports) ou alterações pedidas explicitamente como "pode fazer", "faça", "implemente" não precisam de confirmação.
- Ao final, informar de forma concisa o que foi modificado e onde.

## Documentação obrigatória

- `docs/especificacao.md` — contrato normativo. **Leia antes de qualquer implementação.**
- `docs/panorama-atual.md` — arquivo-base de status. **Toda implementação, correção ou decisão relevante deve atualizá-lo no mesmo commit da mudança.**
- `docs/explicacao-codigo.md` — explicação didática do código (conceitos Python × Delphi e módulos/métodos do projeto). **Toda alteração relevante de código deve atualizá-lo no mesmo commit.** Regras: todo módulo/método público explicado; referenciar sempre **arquivo + nome do método** (nunca números de linha); comparações com Delphi ficam apenas neste documento.

## Organização da documentação

- `docs/` — documentação interna de desenvolvimento (contrato, status, explicação do código). **Local apenas: está no `.gitignore` e NÃO vai para o repositório.**
- `public/docs/` — documentação pública do projeto. **Toda documentação nova DEVE ser criada em `public/docs/`** (versionada, faz parte do site).
- `README.md` — cartão de visita público do projeto. **Atualizar sempre que houver mudança visível ao público** (novo recurso, mudança de stack, requisitos de instalação). **Somente conteúdo público:** NÃO incluir informações de IA, processo de construção, milestones internos ou referências a `docs/` e `codemap.md`.

## Organização do código

| Pasta | Responsabilidade |
|---|---|
| `src/app.py` | Aplicação Flask + rotas de página e API JSON; `iniciar_scheduler()` — M3 |
| `src/motores/` | Motores de coleta multi-API (contrato `MotorBase`; motor `dadosjah`) — Fases 1–2 |
| `src/scripts/` | Scripts de operação: `configurar.py` (primeiro boot: gera a master key e o schema) — M2 |
| `src/jobs/` | Tarefas agendadas: `coletar.py` (ciclo de coleta), `reter.py` (retenção de dados e logs) — M1 |
| `src/services/` | Regras de negócio: `classificar.py` (cStat → estado), `api_dadosjah.py` (cliente HTTP), `auth_dadosjah.py` (login/logout) — M1 |
| `src/utils/` | Utilitários: `settings.py`, `logger.py`, `db.py`, `config.py` (lê `config.json`), `segredos.py` (criptografia), `rate_limit.py` (rate limit das APIs), `turnstile.py` (anti-bot opcional) |
| `src/web/` | Templates Jinja2 (`templates/`) e estáticos (`static/`) — M3 |

Pastas novas devem seguir essa separação por responsabilidade.

## Configuração da instalação

- **Operacional em `config.json`** (raiz do projeto), copiado de `config.example.json`:
  `cp config.example.json config.json`. Seções: `coleta` (UFs, modelos, intervalo, timeout, motor), `retencao` (dados_dias, logs_dias), `web` (porta, padrão 5628), `rate_limit` (api_requisicoes_por_minuto) e `links` (github, ctec). É lido uma vez no import: **alterações exigem restart do processo**.
- **Segredos e chaves de boot no `.env`** (copiado de `.env.example`), nunca versionado: credenciais da API (`API_LOGIN_*`), `MONITOR_MASTER_KEY`, `TURNSTILE_*`, `SESSION_COOKIE_SECURE`; `UFS`/`TP_AMBS` como fallback, `BANCO_CAMINHO` e `LOG_NIVEL`.
- **Não há interface web de configuração** (removida por decisão de segurança): as configurações são feitas no deploy.

## Convenções de código Python

- Todo script executável em `src/` deve incluir, no topo, o bootstrap que coloca a raiz do projeto no `sys.path`:
  `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))`.
  Exceção: `src/app.py` está um nível acima (direto em `src/`) e usa `parents[1]`.
- Arquivos `.py`: **UTF-8** — docstrings e comentários em Português do Brasil **com acentos** (decisão v2; projeto open-source didático).
- **Docstrings Google-style** (`Args:`/`Returns:`) em toda função pública.
- Comentários no corpo com **detalhe extra em trechos complexos** (criptografia, agendamento, concorrência SQLite) para programadores externos entenderem.
- Sem overcomment em linhas óbvias; comparações com Delphi ficam apenas em `docs/explicacao-codigo.md`.
- Imports absolutos: `from src.utils.settings import ...`.
- `if __name__ == "__main__"` em todo módulo executável.

## Encoding — CRÍTICO

- Arquivos `.md`: **UTF-8 sem BOM**, em Português do Brasil.
- Arquivos `.py`: **UTF-8 sem BOM** (acentos permitidos em docstrings/comentários; nomes de identificadores em ASCII).
- Arquivos `.bat`: **sem acentos** (ASCII).
- **NUNCA use PowerShell para gravar/editar arquivos** — ele insere BOM e corrompe acentos. Use as ferramentas de escrita/edição dedicadas.
- Preserve o encoding original dos arquivos — nunca converta ANSI ↔ UTF-8 sem intenção explícita.
- **Verificação pós-edição:** após qualquer edição, confirmar que acentos/caracteres especiais permaneceram intactos e que `.md` não ganhou BOM.

## Banco de dados

- SQLite em modo WAL, arquivo único em `data/` (caminho via `BANCO_CAMINHO` no `.env`).
- Tabelas (schema completo em `src/utils/db.py`):
  - `leituras` — histórico de status por UF × documento × ambiente
  - `modelos_dfe` — modelos de DFe suportados (extensível por dados; seed `nfe`)
  - `segredos` — credenciais criptografadas (Fernet: AES-128-CBC + HMAC-SHA256)
- A antiga tabela `configuracoes` foi **removida**; o operacional vive em `config.json`.
- Retenção de dados e logs por job diário conforme `config.json` (`retencao.dados_dias`, `retencao.logs_dias`).
- Logs em pasta mensal: `logs/AAAAMM/<modulo>_<AAAAMMDD>.log` (um arquivo por dia, sem rotação automática; limpeza por idade no job de retenção).

## Segurança

- **Master key** (`MONITOR_MASTER_KEY`) no `.env` (nunca versionado); segredos reversíveis (ex.: `api_token`) criptografados na tabela `segredos` (Fernet: AES-128-CBC + HMAC-SHA256; chave derivada por PBKDF2-HMAC-SHA256 600k).
- **Autenticação por ciclo:** o coletor faz login no início do ciclo, reaproveita o mesmo token e faz logout no fim; o token vive apenas em memória.
- **APIs públicas protegidas:** rate limit por IP (`src/utils/rate_limit.py`) e Cloudflare Turnstile **opcional** (`src/utils/turnstile.py`); CSP estrita em todas as respostas.
- **Sem autenticação de interface:** a área administrativa de configuração foi removida (configs só no deploy).
- Nunca logar segredos, nunca expor credenciais em páginas públicas ou no repositório.
- `.env.example` documenta as chaves sem valores sensíveis.

## Execução

- **Caminho simples (sem nginx):** `python src/app.py` — sobe em `0.0.0.0` na porta de `web.porta` (padrão 5628).
- **Caminho avançado (opcional):** gunicorn com **1 worker** via `wsgi:app` (o scheduler roda no processo; mais de um worker duplicaria coletas), atrás de nginx.
- **Container:** há `Dockerfile`; monte volumes em `data/` e `logs/`.
- **Verificação:** `python -m pytest tests -q` (rotas/regras via test_client) e `python src/scripts/verificar.py` (smoke HTTP em servidor real, porta efêmera, encerra sozinho).

## Open-source (decisões v2)

- Licença **MIT**, copyright **DadosJah**.
- **`AGENTS.md` É versionado de propósito** (diferente do `olist-tiny-code-auth`).
- README, `llms.txt`, `robots.txt`, `sitemap.xml`, termos de uso e docs de hospedagem fazem parte do escopo (M4). Documentação pública deve ficar em `public/docs/`.
- Logos: **somente logos DadosJah** (`src/web/static/logos/`); sem logos de terceiros.
- Rodapé das páginas credita "Desenvolvido e mantido pela CTEC" (`https://ctec.com.br/`).
