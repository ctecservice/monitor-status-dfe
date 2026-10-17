# Arquitetura

Visão em alto nível de como o Monitor Status DFe está organizado e de como uma leitura percorre o sistema.

## Diagrama geral

```
                        ┌─────────────────────────┐
                        │        Navegador         │
                        └───────────┬─────────────┘
                                    │ HTTP
                                    ▼
┌────────────────────────────────────────────────────────────┐
│                        Aplicação Flask                       │
│                                                              │
│   Rotas de página             Rotas de API JSON              │
│   (/, /uf/<uf>, /termos)      (/api/status, /api/uf/...)     │
│   + /health                   [+ rate limit, Turnstile]      │
│                          │                                   │
│                          ▼                                   │
│   ┌───────────────────────────────────────────────────┐     │
│   │              Camada de serviços                    │     │
│   │   classificação do cStat                           │     │
│   └───────────────┬───────────────────────────────────┘     │
│                   │                                          │
│      ┌────────────▼────────┐   ┌──────────────────────┐      │
│      │   Jobs agendados     │   │  Utilitários          │      │
│      │  coleta · retenção   │   │ config · banco · log  │      │
│      └────────────┬─────────┘   │ segredos · rate limit │      │
│                   │             └──────────────────────┘      │
└───────────────────┼─────────────────────────────────────────┘
                    │ HTTP (login por ciclo; Bearer token)
                    ▼
      ┌───────────────────────────────────┐
      │   Motores de consulta (src/motores) │
      │   dadosjah · novas APIs (plugáveis) │
      └───────────────┬───────────────────┘
                      │
                      ▼
            ┌──────────────────┐        ┌──────────────────┐
            │  Banco SQLite     │◀──────▶│  Arquivos de log │
            │  (modo WAL)       │        └──────────────────┘
            └──────────────────┘
```

## Componentes

| Componente | Responsabilidade |
|---|---|
| `app.py` | Aplicação Flask: rotas de página, rotas de API JSON, endpoint de saúde e cabeçalhos de segurança. Inicia o agendador e o banco ao subir. |
| `jobs/` | Tarefas agendadas: `coletar` (ciclo periódico de consulta) e `reter` (limpeza diária de dados e logs). |
| `motores/` | Motores de consulta — o ponto de extensão multi-API. Cada API de status é um módulo que implementa o contrato `MotorBase` (autenticar, consultar, encerrar). O motor ativo é escolhido em `config.json` (`coleta.motor`). |
| `services/` | Regras de negócio: classificação do código de status em estado do semáforo. |
| `utils/` | Utilitários transversais: leitura de configuração (`config.json` e `.env`), conexão e esquema do banco, logging, criptografia de segredos, rate limit e verificação anti-robô. |
| `web/` | Interface: templates Jinja2 (`templates/`), estilos, JavaScript e logos (`static/`). |

## Configuração

- **`config.json`** (raiz do projeto) — parâmetros operacionais: UFs e modelos monitorados, intervalo, timeout, motor de coleta, retenções, porta HTTP, rate limit e links. É lido uma vez na inicialização e mantido em memória; alterações exigem restart do processo.
- **`.env`** — segredos e credenciais: URL e credenciais da API, chave mestra, `SESSION_COOKIE_SECURE` e chaves opcionais do Turnstile.

Não há painel web de configuração (decisão de segurança): a configuração é feita por arquivos no deploy.

## Modelo de dados

O banco é um único arquivo SQLite em modo WAL, com três tabelas:

| Tabela | Conteúdo |
|---|---|
| `leituras` | Histórico de status por UF × documento × ambiente (código, motivo, latência, versão, data/hora, erro). |
| `modelos_dfe` | Modelos de DF-e suportados (extensível por dados; seed inicial `nfe`). |
| `segredos` | Credenciais e valores sensíveis armazenados de forma criptografada. |

O índice `idx_leituras_lookup` (UF, documento, ambiente, data de coleta) acelera a busca pela última leitura de cada combinação.

## Proteções das APIs públicas

- **Rate limit por IP.** As rotas `/api/status` e `/api/uf/<uf>/historico` usam um limitador de janela deslizante em memória (padrão 30 requisições por minuto, configurável em `rate_limit.api_requisicoes_por_minuto`). Ao exceder, respondem `429` com `Retry-After: 60`.
- **Anti-robô (Cloudflare Turnstile).** Opcional: quando as chaves estão no `.env`, as mesmas rotas exigem o cabeçalho `CF-Turnstile-Token` e validam o token no servidor; ausente ou inválido resulta em `403`.
- **Cabeçalhos de segurança.** Toda resposta recebe `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` e `Referrer-Policy`.

## Ciclo de vida de uma leitura

1. **Agendamento** — o agendador dispara o ciclo de coleta conforme o intervalo configurado.
2. **Autenticação** — o motor ativo faz login no início do ciclo e obtém o token de acesso, mantido em memória apenas durante o ciclo.
3. **Consulta** — para cada combinação de modelo × UF × ambiente, o motor consulta o endpoint de status, medindo o tempo de resposta. Bate requisitos de timeout definidos em `config.json`.
4. **Classificação** — o código de status devolvido é traduzido em um estado do semáforo; falhas de coleta resultam em "sem dados".
5. **Gravação** — a leitura é gravada na tabela `leituras` com data/hora e os campos técnicos da resposta.
6. **Exibição** — o painel lê a leitura mais recente de cada combinação e a série histórica, montando a grade e o detalhe por UF.
7. **Encerramento** — o motor encerra a sessão no final do ciclo, mesmo em caso de erro.
8. **Retenção** — uma tarefa diária remove leituras e logs mais antigos que os limites configurados, apagando também pastas de log vazias.

## Logs

O logging grava um arquivo por dia dentro de uma pasta por mês, no fuso `America/Sao_Paulo`: `logs/AAAAMM/<modulo>_<AAAAMMDD>.log` (ex.: `logs/202610/app_20261017.log`). Não há rotação por tamanho; a limpeza por idade é feita pelo job de retenção, que apaga arquivos antigos e as pastas mensais vazias.

## Execução

O caminho simples roda o próprio servidor do Flask em `0.0.0.0:5628` (porta configurável), já adequado para uso leve em VPS ou container — **sem nginx obrigatório**. O caminho avançado, com gunicorn + nginx, é opcional e exige exatamente **1 worker** (o agendador roda dentro do processo). Detalhes em [Hospedagem (deploy)](deploy.md).

## Decisões técnicas

- **Flask** — framework web leve, suficiente para as páginas e APIs do monitor, com baixo consumo de recursos.
- **SQLite em modo WAL** — banco em arquivo único, sem servidor dedicado; o modo WAL permite leituras concorrentes com uma escrita sem bloquear o painel.
- **APScheduler** — agendamento em processo, permitindo coletas periódicas e uma tarefa diária de retenção sem depender de `cron` externo.
- **Motores plugáveis** — a integração com a API de consulta é isolada atrás de `MotorBase`, permitindo trocar de API (ou adicionar uma nova) sem tocar no restante do sistema.
- **httpx** — cliente HTTP com suporte a timeouts e medição de tempo de resposta.
- **Criptografia (Fernet + PBKDF2)** — segredos reversíveis são cifrados com Fernet, com chave derivada por PBKDF2 a partir da chave mestra.

## Veja também

- [API JSON](api.md)
- [Configuração](configuracao.md)
- [Hospedagem (deploy)](deploy.md)
