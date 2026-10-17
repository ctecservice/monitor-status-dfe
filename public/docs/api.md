# API JSON

O Monitor Status DFe expõe duas APIs JSON públicas, usadas pelo próprio painel e disponíveis para integração. Todas as respostas são em UTF-8 e no formato JSON.

## Estados e cores

As APIs usam os seguintes estados e cores de semáforo:

| Estado | Valor | Cor |
|---|---|---|
| Operacional | `operacional` | `#22C55E` (verde) |
| Instável | `instavel` | `#F59E0B` (amarelo) |
| Indisponível | `indisponivel` | `#EF4444` (vermelho) |
| Sem dados | `sem_dados` | `#8A8585` (cinza) |

O estado é derivado do código de status (`cStat`) devolvido pela SEFAZ: `107` → operacional, `108` → instável, `109` → indisponível. Qualquer outro valor — ou uma falha de coleta (timeout, rede, HTTP diferente de 200) — resulta em `sem_dados`.

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
      "cor": "#22C55E",
      "cstat": "107",
      "t_med": 320,
      "response_time": 410,
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
| `celulas[].cor` | string | Cor hexadecimal do estado |
| `celulas[].cstat` | string ou null | Código de status da SEFAZ |
| `celulas[].t_med` | número ou null | Tempo médio do serviço informado pela SEFAZ (ms) |
| `celulas[].response_time` | número ou null | Tempo de resposta medido pelo monitor (ms) |
| `celulas[].coletado_em` | string (ISO 8601) | Momento da coleta |
| `celulas[].erro` | string ou null | Mensagem de erro da coleta, quando houver |

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
      "t_med": 305,
      "response_time": 388,
      "erro": null
    }
  ],
  "uptime_pct": 99.2,
  "ultimo": {
    "uf": "MG",
    "documento": "nfe",
    "tp_amb": 1,
    "estado": "operacional",
    "cor": "#22C55E",
    "cstat": "107",
    "t_med": 320,
    "response_time": 410,
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
| `pontos[].t_med` | número ou null | Tempo médio do serviço (ms) |
| `pontos[].response_time` | número ou null | Tempo de resposta medido (ms) |
| `pontos[].erro` | string ou null | Mensagem de erro, quando houver |
| `uptime_pct` | número | Percentual de coletas operacionais na janela (1 casa decimal) |
| `ultimo` | objeto | Último status conhecido; nunca é `null` |
| `ultimo.msg` | string ou null | Mensagem (`Msg`) devolvida pela SEFAZ |
| `ultimo.x_motivo` | string ou null | Motivo (`xMotivo`) devolvido pela SEFAZ |
| `ultimo.ver_aplic` | string ou null | Versão da aplicação da SEFAZ |
| `ultimo.dh_recebto` | string ou null | Data/hora de recebimento informada pela SEFAZ |

> Quando não há leitura na combinação, `ultimo` ainda é devolvido com `estado` e `cor` iguais a `sem_dados` e os demais campos `null`.

### Erros

| Situação | Status HTTP | Corpo |
|---|---|---|
| UF inválida | 404 | `{ "erro": "UF inválida." }` |
| `horas` não numérico | 400 | `{ "erro": "Parâmetro 'horas' inválido." }` |
| `horas` fora de 1–720 | 400 | `{ "erro": "Parâmetro 'horas' deve estar entre 1 e 720." }` |
| `tp_amb` não numérico | 400 | `{ "erro": "Parâmetro 'tp_amb' inválido." }` |

---

## `GET /health`

Endpoint de saúde do monitor, sem autenticação.

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
| `status` | string | `ok` quando o endpoint responde |
| `banco` | string | `ok` se o banco respondeu; `erro` em caso de falha |
| `scheduler` | string | `ativo` quando o agendador está rodando; `inativo` caso contrário |
| `ultima_coleta` | string ou null | Momento da leitura mais recente |
| `leituras_total` | número | Total de leituras armazenadas |

## Veja também

- [Uso do painel](uso.md)
- [Arquitetura](arquitetura.md)
