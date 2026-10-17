# AGENTS.md — Monitor Status DFe

> Monitor web open-source de status dos servicos SEFAZ (DF-e), alimentado pela API DadosJah.
> Stack: Python 3.12 + Flask + SQLite + APScheduler + Jinja2 + HTML/CSS/JS vanilla.
> Local: `D:\Dev\Python\monitor-status-dfe`

## Leitura obrigatoria (ordem para retomar o projeto em uma nova sessao)

1. `docs/panorama-atual.md` — estado real do projeto (fase atual, decisoes, roadmap)
2. `docs/implementation_plan.md` — plano v2 (open-source) com milestones M0–M5 e criterios de aceite
3. `docs/especificacao.md` — contrato normativo (requisitos, arquitetura, modelo de dados)
4. `codemap.md` — mapa do codigo por pasta

## Comunicacao

- Responder sempre em Portugues do Brasil, de forma clara, objetiva e didatica.
- Ao explicar codigo Python, incluir breve comparacao com Delphi quando for util.

## Workflow

- Antes de alterar codigo, apresentar um **plano resumido** (o que muda, em quais arquivos, qual abordagem) e aguardar confirmacao quando a mudanca afetar **3+ arquivos** ou alterar a arquitetura.
- Correcoes triviais (tipagem, sintaxe, imports) ou alteracoes pedidas explicitamente como "pode fazer", "faca", "implemente" nao precisam de confirmacao.
- Ao final, informar de forma concisa o que foi modificado e onde.

## Documentacao obrigatoria

- `docs/especificacao.md` — contrato normativo. **Leia antes de qualquer implementacao.**
- `docs/panorama-atual.md` — arquivo-base de status. **Toda implementacao, correcao ou decisao relevante deve atualiza-lo no mesmo commit da mudanca.**
- `docs/explicacao-codigo.md` — explicacao didatica do codigo (conceitos Python x Delphi e modulos/metodos do projeto). **Toda alteracao relevante de codigo deve atualiza-lo no mesmo commit.** Regras: todo modulo/metodo publico explicado; referenciar sempre **arquivo + nome do metodo** (nunca numeros de linha); comparacoes com Delphi ficam apenas neste documento.

## Organizacao da documentacao

- `docs/` — documentacao interna de desenvolvimento (contrato, status, explicacao do codigo). **Local apenas: esta no `.gitignore` e NAO vai para o repositorio.**
- `public/docs/` — documentacao publica do projeto. **Toda documentacao nova DEVE ser criada em `public/docs/`** (versionada, faz parte do site).
- `README.md` — cartao de visita publico do projeto. **Atualizar sempre que houver mudanca visivel ao publico** (novo recurso, mudanca de stack, requisitos de instalacao). **Somente conteudo publico:** NAO incluir informacoes de IA, processo de construcao, milestones internos ou referencias a `docs/` e `codemap.md`.

## Organizacao do codigo

| Pasta | Responsabilidade |
|---|---|
| `src/app.py` | Aplicacao Flask + rotas de pagina e API JSON — M3 |
| `src/scripts/` | Scripts de operacao: `configurar.py` (primeiro boot: master key, senha admin) — M2 |
| `src/jobs/` | Tarefas agendadas: `coletar.py` (ciclo de coleta), `reter.py` (retencao de dados e logs) — M1 |
| `src/services/` | Regras de negocio: `classificar.py` (cStat -> estado), `api_dadosjah.py` (cliente HTTP) — M1 |
| `src/utils/` | Utilitarios: `settings.py`, `logger.py`, `db.py`, `config.py` (configuracoes no banco), `segredos.py` (criptografia) |
| `src/web/` | Templates Jinja2 (`templates/`) e estaticos (`static/`) — M3 |

Pastas novas devem seguir essa separacao por responsabilidade.

## Convencoes de codigo Python

- Todo script executavel em `src/` deve incluir, no topo, o bootstrap que coloca a raiz do projeto no `sys.path`:
  `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))`.
- Arquivos `.py`: **UTF-8** — docstrings e comentarios em Portugues do Brasil **com acentos** (decisao v2; projeto open-source didatico).
- **Docstrings Google-style** (`Args:`/`Returns:`) em toda funcao publica.
- Comentarios no corpo com **detalhe extra em trechos complexos** (criptografia, agendamento, concorrencia SQLite) para programadores externos entenderem.
- Sem overcomment em linhas obvias; comparacoes com Delphi ficam apenas em `docs/explicacao-codigo.md`.
- Imports absolutos: `from src.utils.settings import ...`.
- `if __name__ == "__main__"` em todo modulo executavel.

## Encoding — CRITICO

- Arquivos `.md`: **UTF-8 sem BOM**, em Portugues do Brasil.
- Arquivos `.py`: **UTF-8 sem BOM** (acentos permitidos em docstrings/comentarios; nomes de identificadores em ASCII).
- Arquivos `.bat`: **sem acentos** (ASCII).
- **NUNCA use PowerShell para gravar/editar arquivos** — ele insere BOM e corrompe acentos. Use as ferramentas de escrita/edicao dedicadas.
- Preserve o encoding original dos arquivos — nunca converta ANSI <-> UTF-8 sem intencao explicita.
- **Verificacao pos-edicao:** apos qualquer edicao, confirmar que acentos/caracteres especiais permaneceram intactos e que `.md` nao ganhou BOM.

## Banco de dados

- SQLite em modo WAL, arquivo unico em `data/` (caminho via `BANCO_CAMINHO` no `.env`).
- Tabelas (schema completo em `src/utils/db.py`):
  - `leituras` — historico de status por UF x documento x ambiente
  - `modelos_dfe` — modelos de DFe suportados (extensivel por dados; seed `nfe`)
  - `configuracoes` — filtros operacionais (UFs, modelos, intervalo, timeout, retencoes)
  - `segredos` — credenciais criptografadas (AES-GCM)
- Retencao de dados e logs por job diario conforme `configuracoes` (`retencao_dados_dias`, `retencao_logs_dias`).

## Seguranca

- **Master key** (`MONITOR_MASTER_KEY`) no `.env` (nunca versionado); segredos reversiveis (ex.: `api_token`) criptografados na tabela `segredos` (Fernet/AES-GCM com chave derivada por PBKDF2).
- Senha do admin da pagina `/config` armazenada como hash (irreversivel).
- Nunca logar segredos, nunca expor credenciais em paginas publicas ou no repositorio.
- `.env.example` documenta as chaves sem valores sensiveis.

## Open-source (decisoes v2)

- Licenca **MIT**, copyright **DadosJah**.
- **`AGENTS.md` E versionado de proposito** (diferente do `olist-tiny-code-auth`).
- README, `llms.txt`, `robots.txt`, `sitemap.xml`, termos de uso e docs de hospedagem fazem parte do escopo (M4). Documentacao publica deve ficar em `public/docs/`.
- Logos: **somente logos DadosJah** (`src/web/static/logos/`); sem logos de terceiros.
