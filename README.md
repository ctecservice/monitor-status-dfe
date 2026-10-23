# Monitor Status DFe

> Monitor web open-source de status dos serviços SEFAZ (DF-e), alimentado pela API DadosJah.

[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1-black.svg)](https://flask.palletsprojects.com/)

Página que acompanha a disponibilidade dos serviços de emissão de documentos fiscais eletrônicos nas SEFAZ de todos os estados brasileiros.

## Sobre o projeto

O Monitor Status DFe consulta periodicamente o status dos serviços SEFAZ usados na emissão de DF-e (NF-e e NFC-e) e mostra, em uma única página, quais estados estão operacionais, instáveis ou indisponíveis — informação útil para quem emite ou depende da emissão desses documentos.

Os dados são obtidos da API DadosJah, que consulta o ambiente nacional de DF-e. O monitor organiza, classifica e guarda esse histórico; ele não substitui os canais oficiais da SEFAZ.

## Recursos

- Painel com três visualizações: **grade** (semáforo por UF), **cards** (resumo por UF) e **gráfico de linha** de latência com uma linha por UF
- Alternância entre **produção** e **homologação**, e filtro por documento (**NF-e / NFC-e**)
- Página de detalhe por UF: último status, uptime, gráfico de latência, incidentes recentes e coletas recentes com exportação **CSV/JSON**
- Atualização automática do painel a cada 60 segundos (com botão de atualização manual)
- Coleta, retenção de dados/logs e backup diário do banco agendados automaticamente
- **API JSON pública** (`/api/status`, `/api/historico`, `/api/uf/<uf>/historico`) com limite de requisições por IP e proteção anti-robô opcional (Cloudflare Turnstile)
- Página **API** no site com a documentação interativa (Swagger UI), download da especificação OpenAPI e coleção Postman
- **Modo embed** (`/?embed=1`): o painel pode ser incorporado em outras páginas via iframe, sem barra superior nem rodapé
- Frontend **estático** (HTML/CSS/JS vanilla, sem build): pode ser publicado separadamente na Vercel ou Cloudflare Pages, com a API em outro domínio (CORS liberado)
- Consulta modular: novas APIs de consulta entram como módulos (motores), além da DadosJah
- Endpoint de saúde do monitor (`/health`) e páginas de FAQ e termos de uso

## Privacidade e segurança

- **Não coleta dados de visitantes.** O monitor não usa cookies de rastreamento, não registra dados pessoais de quem acessa o painel e não compartilha informações com terceiros.
- **As leituras são dados técnicos públicos.** O histórico armazenado contém apenas informações de status dos serviços SEFAZ (código, motivo, latência, versão da aplicação) — sem qualquer dado pessoal ou fiscal de contribuintes.
- **Credenciais do operador ficam locais.** As credenciais de acesso à API e a chave mestra residem somente no arquivo `.env` da instalação, que não é versionado.
- **Sem painel de administração web.** Por decisão de segurança, o monitor não expõe nenhuma tela de configuração pela rede: as configurações operacionais ficam no arquivo `config.json` da raiz, aplicadas apenas no momento do deploy.
- **Token de acesso em memória.** O token de acesso à API é mantido apenas em memória durante o ciclo de coleta e nunca é gravado em disco nem em log.
- **APIs públicas protegidas.** As APIs JSON aplicam limite de requisições por IP (padrão 30 por minuto) e podem habilitar, de forma opcional, a verificação anti-robô Cloudflare Turnstile.
- O tratamento segue princípios da LGPD: não há coleta de dados pessoais de visitantes nem de contribuintes.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Backend web | Flask |
| Agendamento | APScheduler |
| Banco de dados | SQLite (modo WAL) |
| Cliente HTTP | httpx |
| Criptografia | cryptography (Fernet + PBKDF2) |
| Frontend | HTML/CSS/JS vanilla (estático, sem build tools) |

## Como executar

Pré-requisito: Python 3.12 instalado e disponível no PATH.

No Windows:

1. `criar-venv.bat` — cria o ambiente virtual `.venv` e instala as dependências.
2. Copie `.env.example` para `.env` e `config.example.json` para `config.json`, e ajuste os valores (credenciais da API de consulta e configurações operacionais).
3. `entrar-venv.bat` — abre o terminal com o ambiente virtual ativado.
4. `python src/scripts/configurar.py` — primeiro boot: gera a chave mestra e cria as tabelas do banco.
5. `python src/app.py` — inicia o monitor (backend + frontend, que é servido da pasta `frontend/`).

Acesse `http://localhost:5628` (a porta é configurável em `config.json`, em `web.porta`).

No Linux (VPS) e em container, veja [`public/docs/deploy.md`](public/docs/deploy.md) — inclui os caminhos simples (Flask direto), avançado (gunicorn + nginx), Docker, Coolify, e a publicação do frontend na Vercel/Cloudflare Pages. Instruções detalhadas e solução de problemas: [`public/docs/como-executar.md`](public/docs/como-executar.md).

## Como configurar

A configuração é dividida em dois arquivos, ambos criados a partir dos exemplos e que não devem ser versionados:

**`.env`** (copiado de `.env.example`) — segredos e credenciais:

| Variável | Descrição |
|---|---|
| `API_BASE_URL` | URL base da API de consulta |
| `API_TIMEOUT_S` | Timeout (segundos) das requisições à API |
| `API_LOGIN_USUARIO` | Usuário de login da API |
| `API_LOGIN_SENHA` | Senha de login da API |
| `MONITOR_MASTER_KEY` | Chave mestra do monitor (gerada pelo primeiro boot) |
| `SESSION_COOKIE_SECURE` | Restringe o cookie de sessão a HTTPS (`true` em produção) |
| `TURNSTILE_SITE_KEY` | Chave pública do Cloudflare Turnstile (opcional) |
| `TURNSTILE_SECRET_KEY` | Chave secreta do Cloudflare Turnstile (opcional) |
| `UFS` | UFs monitoradas, usadas como padrão (siglas separadas por vírgula) |
| `TP_AMBS` | Ambientes: `1` = produção, `2` = homologação |
| `DELAY_ENTRE_CONSULTAS_S` | Pausa entre consultas do ciclo de coleta (segundos), para respeitar o rate limit da API de consulta (padrão `0.5`) |
| `BANCO_CAMINHO` | Caminho do arquivo SQLite |
| `LOG_NIVEL` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `PORT` | Porta HTTP (tem prioridade sobre `web.porta`; útil em PaaS) |
| `EMBED_ORIGENS` | Origens autorizadas a incorporar o painel em iframe (`/?embed=1`), separadas por espaço |

> **Turnstile é opcional.** Sem as duas chaves preenchidas, a proteção anti-robô fica desligada.

**`config.json`** (copiado de `config.example.json`) — parâmetros operacionais:

| Chave | Descrição |
|---|---|
| `coleta.ufs_monitoradas` | UFs monitoradas (vazio = padrão do `.env`) |
| `coleta.modelos_ativos` | Modelos de DFe consultados (ex.: `nfe,nfce`) |
| `coleta.intervalo_min` | Intervalo entre ciclos de coleta, em minutos |
| `coleta.timeout_s` | Timeout das requisições, em segundos |
| `coleta.motor` | Motor de consulta ativo (ex.: `dadosjah`) |
| `retencao.dados_dias` | Dias de retenção do histórico de leituras |
| `retencao.logs_dias` | Dias de retenção dos arquivos de log |
| `web.porta` | Porta HTTP da aplicação (padrão `5628`) |
| `rate_limit.api_requisicoes_por_minuto` | Limite de requisições por IP na API pública (padrão `30`) |

Alterações no `config.json` passam a valer **após reiniciar a aplicação**.

Detalhes completos em [`public/docs/configuracao.md`](public/docs/configuracao.md).

## Multi-API (motores)

A integração com a API de consulta é modular. Cada API é implementada como um **motor** em `src/motores/`, e o motor ativo é escolhido em `config.json` (`coleta.motor`). Hoje o projeto traz o motor `dadosjah`; uma nova API entra como um novo módulo, sem alterar o restante do sistema. Cada motor autentica no início do ciclo de coleta, reutiliza o mesmo token em todas as consultas e encerra a sessão no final.

## Estrutura do projeto

```
frontend/               # Frontend estático (100% autônomo — Vercel/Pages)
├── index.html          # Painel (grade, cards, gráfico de linha)
├── detalhe.html        # Detalhe da UF (?uf=&doc=&amb=)
├── faq.html            # FAQ
├── termos.html         # Termos de uso
├── api.html            # Documentação da API (Swagger UI + Postman)
├── css/  js/  assets/  vendor/
src/                    # Backend (Flask + jobs + API JSON)
├── app.py              # Serve o frontend/ + APIs JSON
├── scripts/            # Scripts de operação (primeiro boot: configurar.py)
├── jobs/               # Tarefas agendadas (coleta, retenção, backup)
├── motores/            # Motores de consulta (integração com APIs de status)
├── services/           # Regras de negócio (classificação de status, cliente da API)
└── utils/              # Utilitários (configuração, banco, logs, segredos, rate limit)
public/                 # Documentação pública do site (docs/ e api/openapi.yaml)
postman/                # Coleção Postman da API
tests/                  # Testes automatizados (pytest)
```

## Rotas

| Rota | Tipo | Descrição |
|---|---|---|
| `/` | página | Painel principal (grade, cards e gráfico de linha) |
| `/detalhe.html?uf=&doc=&amb=` | página | Detalhe de uma UF (uptime, gráfico, incidentes, coletas) |
| `/faq`, `/termos` | página | FAQ e termos de uso |
| `/api/status` | JSON | Estado atual das células do painel + lista de modelos |
| `/api/historico` | JSON | Séries históricas de todas as UFs (gráfico de linha) |
| `/api/uf/<uf>/historico` | JSON | Série histórica de uma UF |
| `/api/openapi.yaml` | arquivo | Especificação OpenAPI da API |
| `/health` | JSON | Saúde do monitor (banco, agendador, última coleta) |

A referência completa das APIs JSON está em [`public/docs/api.md`](public/docs/api.md). Há também a [especificação OpenAPI](public/api/openapi.yaml) e a [coleção Postman](https://documenter.getpostman.com/view/53424652/2sBYHUTLTg) prontas para importar em ferramentas de integração e teste.

## Documentação

Índice da documentação pública: [`public/docs/`](public/docs/README.md).

- [Como executar](public/docs/como-executar.md)
- [Uso do painel](public/docs/uso.md)
- [Configuração](public/docs/configuracao.md)
- [API JSON](public/docs/api.md)
- [Arquitetura](public/docs/arquitetura.md)
- [Hospedagem (deploy)](public/docs/deploy.md)
- [Termos de uso](public/docs/termos-uso.md)

## Licença

MIT — DadosJah. Projeto open-source desenvolvido e mantido pela [CTEC](https://ctec.com.br/).
