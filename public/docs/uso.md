# Uso do painel

Este documento descreve o uso diário das telas públicas do Monitor Status DFe.

## Painel principal (`/`)

A página inicial mostra uma grade com as **UFs nas linhas** e os **documentos fiscais nas colunas** (por exemplo, NF-e). Cada célula é um semáforo do estado atual do serviço daquela UF para aquele documento.

### Grade e semáforo

Cada célula exibe:

- o **estado** do serviço (operacional, instável, indisponível ou sem dados);
- a **latência** medida (em milissegundos), quando disponível;
- o **código de status** (`cStat`) devolvido pela SEFAZ.

As cores seguem a legenda exibida abaixo do cabeçalho:

| Estado | Cor | Significado |
|---|---|---|
| Operacional | verde | Serviço respondendo normalmente (`cStat` 107) |
| Instável | amarelo | Serviço com comportamento degradado (`cStat` 108) |
| Indisponível | vermelho | Serviço fora do ar (`cStat` 109) |
| Sem dados | cinza | A fonte não respondeu (API, rede, certificado ou timeout) |

Clique em qualquer célula para abrir a página de detalhe daquela UF.

### Toggle de ambiente

No topo da grade há um seletor com os ambientes **Produção** e **Homologação**. Ele alterna qual ambiente é exibido:

- **Produção** (`tpAmb` 1) — ambiente real de emissão.
- **Homologação** (`tpAmb` 2) — ambiente de testes.

A grade é atualizada automaticamente a cada **60 segundos**, buscando os dados mais recentes.

### "Sem dados" × "Indisponível"

É importante não confundir os dois estados:

- **Sem dados** indica problema entre o monitor e a fonte: a API não respondeu, houve falha de rede, erro de certificado ou timeout. O monitor não conseguiu saber o estado real do serviço.
- **Indisponível** indica que a fonte respondeu e informou que o **serviço SEFAZ está fora do ar** (`cStat` 109).

## Página de detalhe da UF (`/uf/<uf>`)

Ao clicar em uma UF no painel, abre-se a página de detalhe. Ela traz:

- **Último status** — estado, motivo (`xMotivo`), `cStat`, versão da aplicação da SEFAZ, latência, data de recebimento e data da coleta.
- **Uptime 24 h** — percentual de coletas com estado operacional nas últimas 24 horas.
- **Latência — últimas 24 h** — gráfico no estilo sparkline em que cada ponto representa uma coleta; passe o mouse sobre os pontos para ver o detalhe.
- **Documento** — botões para alternar entre os modelos de DF-e disponíveis para aquela UF.

A página também permite alternar o ambiente (Produção / Homologação) no topo.

## Painel de configuração (`/config`)

O painel `/config` ajusta os filtros operacionais do monitor e é **protegido por senha**. Na primeira visita, exibe um formulário de login; após autenticar, mostra o formulário de configuração.

> A senha do painel é definida no primeiro boot, ao rodar `python src/scripts/configurar.py`. Consulte [Configuração](configuracao.md).

Os filtros disponíveis são:

| Filtro | O que faz |
|---|---|
| UFs monitoradas | Restringe a coleta a determinadas UFs (vazio = todas) |
| Modelos ativos | Restringe a coleta a determinados documentos (vazio = todos os ativos) |
| Intervalo entre coletas | Frequência do ciclo de coleta, em minutos (1 a 1440) |
| Timeout da API | Tempo máximo de espera por resposta da API, em segundos (1 a 120) |
| Retenção de dados | Por quantos dias o histórico de leituras é mantido (mínimo 1) |
| Retenção de logs | Por quantos dias os arquivos de log são mantidos (mínimo 1) |

As alterações são aplicadas ao ciclo seguinte, sem reiniciar a aplicação. A retenção é aplicada por uma tarefa diária.

Ao terminar, use o botão **Sair** para encerrar a sessão do painel.

## Endpoint de saúde (`/health`)

O endpoint `/health` devolve um JSON com a situação do monitor, útil para monitoramento externo e verificações automáticas:

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
| `status` | `ok` quando o endpoint responde |
| `banco` | `ok` se o banco respondeu; `erro` em caso de falha |
| `scheduler` | `ativo` quando o agendador está em execução; `inativo` caso contrário |
| `ultima_coleta` | Data/hora da leitura mais recente |
| `leituras_total` | Total de leituras armazenadas |

## Próximos passos

- [Configuração](configuracao.md) — detalhes das variáveis e limites.
- [API JSON](api.md) — como consumir os dados programaticamente.
