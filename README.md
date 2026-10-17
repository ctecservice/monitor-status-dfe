# Monitor Status DFe

> Monitor web open-source de status dos serviços SEFAZ (DF-e), alimentado pela API DadosJah.

[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-3.1-black.svg)](https://flask.palletsprojects.com/)

Página que acompanha a disponibilidade dos serviços de emissão de documentos fiscais eletrônicos nas SEFAZ de todos os estados brasileiros.

## Sobre o projeto

O Monitor Status DFe é uma aplicação web que consulta periodicamente o status dos serviços SEFAZ usados na emissão de DF-e (Documentos Fiscais Eletrônicos). O objetivo é dar visibilidade rápida, em uma única página, de quais estados estão operacionais, instáveis ou indisponíveis — informação útil para quem emite ou depende da emissão de NF-e e outros documentos.

Os dados são obtidos da API DadosJah, que consulta o ambiente nacional de DF-e. O monitor apenas organiza, classifica e guarda esse histórico; ele não substitui os canais oficiais da SEFAZ.

## Como funciona

1. **Coleta** — um agendador consulta periodicamente a API de consulta para cada UF, documento fiscal (ex.: NF-e) e ambiente (produção ou homologação).
2. **Classificação** — cada resposta é traduzida em um estado do semáforo (operacional, instável, indisponível ou sem dados) a partir do código de status (`cStat`) devolvido.
3. **Armazenamento** — cada leitura é gravada em um banco SQLite com data/hora, formando um histórico por UF e documento.
4. **Dashboard** — a interface web exibe a grade UF × documento com cores, latência e histórico de disponibilidade (uptime).

## Recursos

- Grade UF × documento com semáforo de status
- Alternância entre produção e homologação
- Latência por serviço (ms) e histórico de disponibilidade (uptime 24 h)
- Página de detalhe por UF com gráfico (sparkline) de latência
- Atualização automática do painel a cada 60 segundos
- Coleta e retenção de dados agendadas de forma automática
- Endpoint de saúde do monitor (`/health`)
- API JSON pública para integração (`/api/status` e `/api/uf/<uf>/historico`), com limite de requisições por IP e proteção anti-robô opcional
- Consulta modular: aceita novas APIs de consulta como módulos (motores), além da DadosJah
- Página pública de [termos de uso](public/docs/termos-uso.md) com aviso transparente sobre rate limit e verificação anti-robô

## Privacidade e segurança

- **Não coleta dados de visitantes.** O monitor não usa cookies de rastreamento, não registra dados pessoais de quem acessa o painel e não compartilha informações com terceiros.
- **As leituras são dados técnicos públicos.** O histórico armazenado contém apenas informações de status dos serviços SEFAZ (código, motivo, latência, versão da aplicação) — sem qualquer dado pessoal ou fiscal de contribuintes.
- **Credenciais do operador ficam locais.** As credenciais de acesso à API e a chave mestra residem somente no arquivo `.env` da instalação, que não é versionado.
- **Sem painel de administração web.** Por decisão de segurança, o monitor não expõe nenhuma tela de configuração pela rede: as configurações operacionais ficam no arquivo `config.json` da raiz, aplicadas apenas no momento do deploy. Isso elimina toda a superfície de ataque de um painel autenticado (login, sessão, formulários).
- **Token de acesso em memória.** O token de acesso à API é mantido apenas em memória durante a execução e nunca é gravado em disco nem em log.
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
| Frontend | Jinja2 + HTML/CSS/JS vanilla |

## Como executar

Pré-requisito: Python 3.12 instalado e disponível no PATH.

No Windows:

1. `criar-venv.bat` — cria o ambiente virtual `.venv` e instala as dependências.
2. Copie `.env.example` para `.env` e `config.example.json` para `config.json`, e ajuste os valores (credenciais da API de consulta e configurações operacionais, por exemplo).
3. `entrar-venv.bat` — abre o terminal com o ambiente virtual ativado.
4. `python src/scripts/configurar.py` — primeiro boot: gera a chave mestra e cria as tabelas do banco.
5. `python src/app.py` — inicia o monitor.

Acesse `http://localhost:5628` (a porta é configurável em `config.json`, em `web.porta`).

Há ainda um `Dockerfile` no repositório para rodar em container. O caminho mais simples de hospedagem usa o próprio servidor do Flask; uma configuração **avançada** com gunicorn + nginx fica documentada em [`public/docs/deploy.md`](public/docs/deploy.md).

Instruções detalhadas (Windows e Linux) e solução de problemas estão em [`public/docs/como-executar.md`](public/docs/como-executar.md).

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
| `BANCO_CAMINHO` | Caminho do arquivo SQLite |
| `LOG_NIVEL` | Nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

> **Turnstile é opcional.** Sem as duas chaves preenchidas, a proteção anti-robô fica desligada.

**`config.json`** (copiado de `config.example.json`) — parâmetros operacionais:

| Chave | Descrição |
|---|---|
| `coleta.ufs_monitoradas` | UFs monitoradas (vazio = padrão do `.env`) |
| `coleta.modelos_ativos` | Modelos de DFe consultados (vazio = todos os ativos) |
| `coleta.intervalo_min` | Intervalo entre ciclos de coleta, em minutos |
| `coleta.timeout_s` | Timeout das requisições, em segundos |
| `coleta.motor` | Motor de consulta ativo (ex.: `dadosjah`) |
| `retencao.dados_dias` | Dias de retenção do histórico de leituras |
| `retencao.logs_dias` | Dias de retenção dos arquivos de log |
| `web.porta` | Porta HTTP da aplicação (padrão `5628`) |
| `rate_limit.api_requisicoes_por_minuto` | Limite de requisições por IP na API pública (padrão `30`) |
| `links.github` | URL do repositório exibida nas páginas |
| `links.ctec` | URL da CTEC exibida no rodapé |

Alterações no `config.json` passam a valer **após reiniciar a aplicação**.

Detalhes completos em [`public/docs/configuracao.md`](public/docs/configuracao.md).

## Multi-API (motores)

A integração com a API de consulta é modular. Cada API é implementada como um **motor** em `src/motores/`, e o motor ativo é escolhido em `config.json` (`coleta.motor`). Hoje o projeto traz o motor `dadosjah`; uma nova API entra como um novo módulo, sem alterar o restante do sistema. Cada motor autentica no início do ciclo de coleta, reutiliza o mesmo token em todas as consultas e encerra a sessão no final.

## Estrutura do projeto

```
src/
├── app.py              # Aplicação Flask (rotas de página e API JSON)
├── scripts/            # Scripts de operação (primeiro boot: configurar.py)
├── jobs/               # Tarefas agendadas (coleta periódica e retenção)
├── motores/            # Motores de consulta (integração com APIs de status)
├── services/           # Regras de negócio (classificação de status)
├── utils/              # Utilitários (configuração, banco, logs, segredos)
└── web/                # Templates Jinja2 e arquivos estáticos
```

## Rotas

| Rota | Tipo | Descrição |
|---|---|---|
| `/` | página | Painel principal (grade UF × documento) |
| `/uf/<uf>` | página | Detalhe de uma UF (uptime, gráfico de latência) |
| `/termos` | página | Termos de uso |
| `/api/status` | JSON | Estado atual das células do painel |
| `/api/uf/<uf>/historico` | JSON | Série histórica de uma UF |
| `/health` | JSON | Saúde do monitor (banco, agendador, última coleta) |

A referência completa das APIs JSON está em [`public/docs/api.md`](public/docs/api.md). Há também uma [especificação OpenAPI](public/api/openapi.yaml) e uma [coleção Postman](postman/collections/Monitor%20Status%20DFe%20API/) prontas para importar em ferramentas de integração e teste.

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
