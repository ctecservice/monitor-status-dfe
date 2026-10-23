# Uso do painel

Este documento descreve o uso diário das telas públicas do Monitor Status DFe.

## Painel principal (`/`)

A página inicial mostra o status dos serviços SEFAZ de todas as UFs monitoradas. Há três **visualizações**, alternadas pelo seletor "Visualização" no topo (a escolha fica salva no navegador):

- **Grade** — semáforo com as UFs nas linhas; cada célula mostra o estado atual do serviço.
- **Cards** — um card por UF com estado, latência e última atualização.
- **Linha** — gráfico de latência (ms) ao longo do tempo, com uma linha por UF; passe o mouse na legenda para destacar uma UF e clique para fixar o destaque.

Os dados são filtrados por dois seletores:

- **Ambiente** — **Produção** (`tpAmb` 1, ambiente real de emissão) ou **Homologação** (`tpAmb` 2, ambiente de testes).
- **Modelo** — documento fiscal consultado (por exemplo, **NF-e** ou **NFC-e**).

### Grade e semáforo

Cada célula exibe:

- o **estado** do serviço (operacional, instável, indisponível ou sem dados);
- a **latência** medida (em milissegundos), quando disponível;
- o **código de status** (`cStat`) devolvido pela SEFAZ.

As cores seguem a legenda exibida no cabeçalho da página:

| Estado | Cor | Significado |
|---|---|---|
| Operacional | verde | Serviço respondendo normalmente (`cStat` 107) |
| Instável | amarelo | Serviço com comportamento degradado (`cStat` 108) |
| Indisponível | vermelho | Serviço fora do ar (`cStat` 109) |
| Sem dados | cinza | A fonte não respondeu (API, rede, certificado ou timeout) |

A latência também é colorida por faixa: **até 2 s** verde (normal), **2 a 5 s** amarelo (lenta) e **acima de 5 s** vermelho (crítica).

Clique em qualquer célula (ou card) para abrir a página de detalhe daquela UF.

O painel é atualizado automaticamente a cada **60 segundos**; o botão **Atualizar** (no topo, ao lado dos seletores) recarrega os dados na hora.

### "Sem dados" × "Indisponível"

É importante não confundir os dois estados:

- **Sem dados** indica problema entre o monitor e a fonte: a API não respondeu, houve falha de rede, erro de certificado ou timeout. O monitor não conseguiu saber o estado real do serviço.
- **Indisponível** indica que a fonte respondeu e informou que o **serviço SEFAZ está fora do ar** (`cStat` 109).

## Página de detalhe da UF (`/detalhe.html?uf=<uf>&doc=<documento>&amb=<ambiente>`)

Ao clicar em uma UF no painel, abre-se a página de detalhe. Ela traz:

- **Último status** — estado, motivo (`xMotivo`), `cStat`, versão da aplicação da SEFAZ, latência, data de recebimento e data da coleta.
- **Uptime** — percentual de coletas com estado operacional na janela selecionada.
- **Latência — histórico** — gráfico de linha com as latências das coletas; a cor dos pontos reflete o estado do serviço; o seletor de janela alterna entre **24 h, 72 h, 7 dias e 30 dias**.
- **Incidentes recentes** — períodos contínuos em que o serviço esteve indisponível na janela.
- **Coletas recentes** — as últimas 20 coletas em tabela, com botões para **exportar em CSV ou JSON**.

A página também permite alternar o ambiente (Produção / Homologação) e o documento (NF-e / NFC-e) no topo, e tem o botão **Atualizar** para recarregar os dados.

## Atualização, rate limit e anti-robô

O dashboard consulta as APIs JSON públicas a cada **60 segundos** para se atualizar. Para preservar o serviço, essas APIs aplicam duas proteções:

- **Limite de requisições por IP** — no máximo 30 requisições por minuto (valor configurável na instalação). Se o limite for excedido, a API devolve `429` e o painel tenta novamente em instantes. Em uso normal do site isso não é perceptível: o polling automático fica bem abaixo do limite.
- **Verificação anti-robô (Cloudflare Turnstile)** — quando habilitada pela instalação, o painel resolve uma verificação anti-robô em segundo plano antes de carregar/atualizar os dados. Ela roda de forma automática e invisível (o visitante normalmente não vê nada nem precisa agir); só em casos excepcionais a Cloudflare pode pedir uma interação. Quando essa proteção está desligada (configuração padrão de desenvolvimento), nada acontece.

## Endpoint de saúde (`/health`)

O endpoint `/health` devolve um JSON com a situação do monitor, útil para monitoramento externo e verificações automáticas. Responde **HTTP 200** quando o banco está acessível e o agendador está ativo; **HTTP 503** caso contrário.

```json
{
  "status": "ok",
  "banco": "ok",
  "scheduler": "ativo",
  "ultima_coleta": "2026-10-16T14:05:00+00:00",
  "leituras_total": 12345
}
```

| Campo | Significado |
|---|---|
| `status` | `ok` (HTTP 200) quando banco e agendador estão saudáveis; `erro` (HTTP 503) caso contrário |
| `banco` | `ok` se o banco respondeu; `erro` em caso de falha |
| `scheduler` | `ativo` quando o agendador está em execução; `inativo` caso contrário |
| `ultima_coleta` | Data/hora da leitura mais recente |
| `leituras_total` | Total de leituras armazenadas |

## Próximos passos

- [Configuração](configuracao.md) — detalhes das variáveis e limites.
- [API JSON](api.md) — como consumir os dados programaticamente.
