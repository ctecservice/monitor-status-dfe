# API JSON

O Monitor Status DFe expõe duas APIs JSON públicas, usadas pelo próprio painel e disponíveis para integração, além do endpoint de saúde. Todas as respostas são em UTF-8 e no formato JSON.

## Endpoints públicos

| Endpoint | Descrição |
|---|---|
| `GET /api/status` | Estado atual de todas as células do painel |
| `GET /api/uf/<uf>/historico` | Série histórica de uma UF |
| `GET /health` | Saúde do monitor (sem rate limit nem anti-robô) |

## Limite de requisições (rate limit)

As rotas `/api/status` e `/api/uf/<uf>/historico` aplicam um limite por endereço IP, com janela de um minuto. O valor padrão é **30 requisições por minuto** e pode ser ajustado em `config.json`, na chave `rate_limit.api_requisicoes_por_minuto`.

Ao exceder o limite, a resposta é:

- status HTTP **`429`**;
- cabeçalho **`Retry-After: 60`**;
- corpo `{ "erro": "Limite de requisições excedido. Tente novamente em instantes." }`.

## Proteção anti-robô (Cloudflare Turnstile)

De forma **opcional**, as duas rotas de dados podem exigir uma verificação anti-robô via Cloudflare Turnstile. A proteção é habilitada quando as chaves `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` estão preenchidas no `.env`; sem elas, fica **desligada**.

Quando habilitada, a requisição deve enviar o token do widget no cabeçalho **`CF-Turnstile-Token`**. Se o cabeçalho estiver ausente ou o token for inválido, a resposta é:

- status HTTP **`403`**;
- corpo `{ "erro": "Verificação anti-bot ausente." }` ou `{ "erro": "Verificação anti-bot falhou." }`.

O endpoint `/health` não está sujeito a rate limit nem à verificação anti-robô.

## Estados e cores

As APIs usam os seguintes estados e cores de semáforo:

| Estado | Valor | Rótulo exibível | Cor |
|---|---|---|---|
| Operacional | `operacional` | `Operacional` | `#22C55E` (verde) |
| Instável | `instavel` | `Instável` | `#F59E0B` (amarelo) |
| Indisponível | `indisponivel` | `Indisponível` | `#EF4444` (vermelho) |
| Sem dados | `sem_dados` | `Sem dados` | `#8A8585` (cinza) |

O estado é derivado do código de status (`cStat`) devolvido pela SEFAZ: `107` → operacional, `108` → instável, `109` → indisponível. Qualquer outro valor — ou uma falha de coleta (timeout, rede, HTTP diferente de 200) — resulta em `sem_dados`. O campo `rotulo` traz o estado pronto para exibição (com acentuação correta).

Campos `cstat`, `t_med` e `response_time` podem ser `null` quando não há dado.

---

## `GET /api/status`

Devolve o estado atual de todas as células do painel: a leitura mais recente de cada combinação UF × documento × ambiente. É o endpoint consumido pelo *polling* do dashboard.

### Exemplo

```
GET /api/status
```

```json
{
  "gerado_em": "2026-10-16T14:05:00+00:00",
  "ambientes": [
    { "tp_amb": 1, "rotulo": "Producao" },
    { "tp_amb": 2, "rotulo": "Homologacao" }
  ],
  "celulas": [
    {
      "uf": "MG",
      "documento": "nfe",
      "tp_amb": 1,
      "estado": "operacional",
      "rotulo": "Operacional",
      "cor": "#22C55E",
      "cstat": "107",
      "t_med": 1000,
      "response_time": 672,
      "coletado_em": "2026-10-16T14:05:00+00:00",
      "erro": null
    }
  ]
}
```

### Campos

| Campo | Tipo | Descrição |
|---|---|---|
| `gerado_em` | string (ISO 8601) | Momento em que a resposta foi gerada |
| `ambientes` | array | Lista de ambientes (`tp_amb` e `rotulo`) |
| `celulas` | array | Leitura mais recente por combinação UF × documento × ambiente |
| `celulas[].uf` | string | Sigla da UF |
| `celulas[].documento` | string | Código do documento (ex.: `nfe`) |
| `celulas[].tp_amb` | número | Ambiente (1 = produção, 2 = homologação) |
| `celulas[].estado` | string | Estado do semáforo |
| `celulas[].rotulo` | string | Rótulo exibível do estado (ex.: `Operacional`, `Instável`, `Indisponível`, `Sem dados`) |
| `celulas[].cor` | string | Cor hexadecimal do estado |
| `celulas[].cstat` | string ou null | Código de status da SEFAZ |
| `celulas[].t_med` | número ou null | Tempo médio do serviço informado pela SEFAZ (`TMed`), convertido de segundos para ms |
| `celulas[].response_time` | número ou null | Tempo de resposta da consulta medido pelo monitor (ms) |
| `celulas[].coletado_em` | string (ISO 8601) | Momento da coleta |
| `celulas[].erro` | string ou null | Mensagem de erro da coleta, quando houver |

> O painel exibe como latência da célula o `response_time` (tempo real da consulta); quando ele não existe, usa `t_med` como alternativa.

---

## `GET /api/uf/<uf>/historico`

Devolve a série histórica de uma UF para um documento e ambiente, incluindo o percentual de uptime e o último status conhecido.

### Parâmetros de consulta

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `documento` | string | primeiro modelo ativo (ex.: `nfe`) | Código do documento |
| `tp_amb` | número | `1` | Ambiente (1 = produção, 2 = homologação) |
| `horas` | número | `24` | Tamanho da janela em horas (1 a 720) |

### Exemplo

```
GET /api/uf/MG/historico?documento=nfe&tp_amb=1&horas=24
```

```json
{
  "uf": "MG",
  "horas": 24,
  "documento": "nfe",
  "tp_amb": 1,
  "pontos": [
    {
      "coletado_em": "2026-10-16T13:00:00+00:00",
      "cstat": "107",
      "estado": "operacional",
      "cor": "#22C55E",
      "t_med": 1000,
      "response_time": 645,
      "erro": null
    }
  ],
  "uptime_pct": 99.2,
  "ultimo": {
    "uf": "MG",
    "documento": "nfe",
    "tp_amb": 1,
    "estado": "operacional",
    "rotulo": "Operacional",
    "cor": "#22C55E",
    "cstat": "107",
    "t_med": 1000,
    "response_time": 672,
    "coletado_em": "2026-10-16T14:05:00+00:00",
    "erro": null,
    "msg": null,
    "x_motivo": "Servico em operacao",
    "ver_aplic": "4.00",
    "dh_recebto": "2026-10-16T14:04:58+00:00"
  }
}
```

### Campos

| Campo | Tipo | Descrição |
|---|---|---|
| `uf` | string | Sigla da UF (normalizada em maiúsculas) |
| `horas` | número | Janela consultada, em horas |
| `documento` | string | Código do documento consultado |
| `tp_amb` | número | Ambiente consultado |
| `pontos` | array | Série de coletas na janela (cada ponto é uma coleta) |
| `pontos[].coletado_em` | string (ISO 8601) | Momento da coleta |
| `pontos[].cstat` | string ou null | Código de status |
| `pontos[].estado` | string | Estado do semáforo |
| `pontos[].cor` | string | Cor hexadecimal do estado |
| `pontos[].t_med` | número ou null | Tempo médio do serviço informado pela SEFAZ (`TMed`), convertido de segundos para ms |
| `pontos[].response_time` | número ou null | Tempo de resposta da consulta medido pelo monitor (ms) |
| `pontos[].erro` | string ou null | Mensagem de erro, quando houver |
| `uptime_pct` | número | Percentual de coletas operacionais na janela (1 casa decimal) |
| `ultimo` | objeto | Último status conhecido; nunca é `null` |
| `ultimo.msg` | string ou null | Mensagem (`Msg`) devolvida pela SEFAZ |
| `ultimo.x_motivo` | string ou null | Motivo (`xMotivo`) devolvido pela SEFAZ |
| `ultimo.ver_aplic` | string ou null | Versão da aplicação da SEFAZ |
| `ultimo.dh_recebto` | string ou null | Data/hora de recebimento informada pela SEFAZ |

> Quando não há leitura na combinação, `ultimo` ainda é devolvido com `estado` = `sem_dados`, `rotulo` = `Sem dados`, `cor` = `#8A8585` e os demais campos `null`.

### Erros

| Situação | Status HTTP | Corpo |
|---|---|---|
| Limite de requisições excedido | 429 | `{ "erro": "Limite de requisições excedido. Tente novamente em instantes." }` (com `Retry-After: 60`) |
| Anti-robô ausente ou inválido (quando habilitado) | 403 | `{ "erro": "Verificação anti-bot ausente." }` ou `{ "erro": "Verificação anti-bot falhou." }` |
| UF inválida | 404 | `{ "erro": "UF inválida." }` |
| `horas` não numérico | 400 | `{ "erro": "Parâmetro 'horas' inválido." }` |
| `horas` fora de 1–720 | 400 | `{ "erro": "Parâmetro 'horas' deve estar entre 1 e 720." }` |
| `tp_amb` não numérico | 400 | `{ "erro": "Parâmetro 'tp_amb' inválido." }` |

---

## `GET /health`

Endpoint de saúde do monitor, sem autenticação, rate limit ou verificação anti-robô. Devolve **HTTP 200** quando o banco está acessível **e** o agendador está ativo; devolve **HTTP 503** quando qualquer um dos dois está em falha.

```json
{
  "status": "ok",
  "banco": "ok",
  "scheduler": "ativo",
  "ultima_coleta": "2026-10-16T14:05:00+00:00",
  "leituras_total": 12345
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `status` | string | `ok` (HTTP 200) quando banco e agendador estão saudáveis; `erro` (HTTP 503) caso contrário |
| `banco` | string | `ok` se o banco respondeu; `erro` em caso de falha |
| `scheduler` | string | `ativo` quando o agendador está rodando; `inativo` caso contrário |
| `ultima_coleta` | string ou null | Momento da leitura mais recente |
| `leituras_total` | número | Total de leituras armazenadas |

## Veja também

- [Uso do painel](uso.md)
- [Arquitetura](arquitetura.md)
- [Especificação OpenAPI](../api/openapi.yaml) e [coleção Postman](../../postman/collections/Monitor%20Status%20DFe%20API/) da API, prontas para importar em ferramentas de integração e teste
