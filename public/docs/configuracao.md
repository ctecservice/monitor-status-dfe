# Configuração

Este documento cobre a configuração do Monitor Status DFe: o primeiro boot, as variáveis do arquivo `.env` e o arquivo `config.json` com os parâmetros operacionais.

## Sem tela de administração web

O monitor **não possui painel web de configuração**. Por decisão de segurança, nenhuma tela de administração é exposta pela rede: não há login, sessão nem formulários de configuração acessíveis publicamente. Toda a configuração é feita por arquivos, aplicada no momento do deploy.

Isso elimina uma superfície de ataque inteira (autenticação, sessões e formulários) e deixa o serviço exposto apenas com as páginas públicas e as APIs JSON.

## Primeiro boot

Antes de iniciar a aplicação pela primeira vez, copie os arquivos de exemplo e ajuste as credenciais da API de consulta:

```
copy .env.example .env
copy config.example.json config.json
```

Depois rode o script de primeiro boot:

```
python src/scripts/configurar.py
```

Esse script (idempotente — pode rodar mais de uma vez com segurança):

1. Gera a **chave mestra** (`MONITOR_MASTER_KEY`) e a grava no `.env`, caso ainda não exista.
2. Cria o esquema do banco de dados (tabelas e valores iniciais).

As credenciais da API e as demais configurações **não** são alteradas por esse script: elas permanecem no `.env` e no `config.json`.

## Variáveis do `.env`

O arquivo `.env.example` documenta todas as chaves. Copie-o para `.env` e ajuste os valores conforme a necessidade. Esse arquivo não deve ser versionado.

| Variável | Descrição | Padrão |
|---|---|---|
| `API_BASE_URL` | URL base da API de consulta | `https://api-dfe.dadosjah.com.br` |
| `API_TIMEOUT_S` | Timeout (segundos) por requisição à API | `20` |
| `API_LOGIN_USUARIO` | Usuário de login da API | *(vazio)* |
| `API_LOGIN_SENHA` | Senha de login da API | *(vazio)* |
| `MONITOR_MASTER_KEY` | Chave mestra do monitor | *(gerada no primeiro boot)* |
| `SESSION_COOKIE_SECURE` | Restringe o cookie de sessão a HTTPS (`true`/`false`) | *(vazio = falso)* |
| `TURNSTILE_SITE_KEY` | Chave pública do Cloudflare Turnstile (anti-robô) | *(vazio = desligado)* |
| `TURNSTILE_SECRET_KEY` | Chave secreta do Cloudflare Turnstile (anti-robô) | *(vazio = desligado)* |
| `UFS` | UFs monitoradas, separadas por vírgula (padrão de fallback) | todas as 27 UFs |
| `TP_AMBS` | Ambientes: `1` = produção, `2` = homologação | `1,2` |
| `DELAY_ENTRE_CONSULTAS_S` | Pausa entre consultas do ciclo de coleta (segundos), para respeitar o rate limit da API de consulta (aceito de 0 a 5) | `0.5` |
| `BANCO_CAMINHO` | Caminho do arquivo SQLite (relativo à raiz do projeto) | `data/statusdfe.db` |
| `LOG_NIVEL` | Nível de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `PORT` | Porta HTTP — tem prioridade sobre `web.porta` (útil em PaaS) | *(vazio)* |
| `EMBED_ORIGENS` | Origens autorizadas a incorporar o painel em iframe (`/?embed=1`), separadas por espaço | `https://dadosjah.com.br https://www.dadosjah.com.br` |

> **Onde colocar valores.** As credenciais da API e a chave mestra são segredos e devem ficar apenas no `.env` da instalação. Não os inclua em repositórios, imagens ou páginas públicas.
>
> **Turnstile é opcional.** A proteção anti-robô das APIs públicas só é ativada quando `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY` estão ambas preenchidas. Sem as chaves, a proteção fica desligada — útil no desenvolvimento.

## Arquivo `config.json`

Os parâmetros operacionais ficam no `config.json` da raiz do projeto, copiado de `config.example.json`. É um único objeto JSON com cinco seções:

```json
{
  "_comentario": "Template de config.json. Copie para config.json e ajuste os valores.",
  "coleta": {
    "ufs_monitoradas": "AC,AL,AP,AM,BA,CE,DF,ES,GO,MA,MT,MS,MG,PA,PB,PR,PE,PI,RJ,RN,RS,RO,RR,SC,SP,SE,TO",
    "modelos_ativos": "nfe,nfce",
    "intervalo_min": 5,
    "timeout_s": 20,
    "motor": "dadosjah"
  },
  "retencao": {
    "dados_dias": 30,
    "logs_dias": 7
  },
  "web": {
    "porta": 5628
  },
  "rate_limit": {
    "api_requisicoes_por_minuto": 30
  }
}
```

| Seção | Chave | Descrição | Padrão |
|---|---|---|---|
| `coleta` | `ufs_monitoradas` | UFs a consultar (siglas separadas por vírgula; vazio = usa o `.env`) | todas as 27 UFs |
| `coleta` | `modelos_ativos` | Modelos de DFe a consultar (vazio = todos os ativos) | `nfe,nfce` |
| `coleta` | `intervalo_min` | Intervalo entre ciclos de coleta, em minutos | `5` |
| `coleta` | `timeout_s` | Timeout das requisições à API, em segundos | `20` |
| `coleta` | `motor` | Motor de consulta ativo (ex.: `dadosjah`) | `dadosjah` |
| `retencao` | `dados_dias` | Dias de retenção do histórico de leituras | `30` |
| `retencao` | `logs_dias` | Dias de retenção dos arquivos de log | `7` |
| `web` | `porta` | Porta HTTP da aplicação | `5628` |
| `rate_limit` | `api_requisicoes_por_minuto` | Limite de requisições por minuto na API pública | `30` |

> **Alterações valem após reiniciar a aplicação.** O `config.json` é lido uma vez, na inicialização do processo, e mantido em memória. Edite o arquivo e reinicie o serviço para aplicar (`python src/app.py` de novo, ou `systemctl restart statusdfe`).
>
> Quando o arquivo não existe ou traz um valor inválido, o monitor usa padrões internos seguros e registra um aviso no log.

## Segurança das configurações

- **Sem painel exposto.** Não há tela de administração pela rede — a configuração é feita por arquivos, no deploy.
- **Segredos no `.env`.** As credenciais da API e a chave mestra ficam apenas no `.env` (não versionado). Em Linux, proteja com `chmod 600 .env`.
- **Chave mestra derivada de contexto.** A chave de sessão do Flask não é a chave mestra em si: é derivada dela por SHA-256 com um domínio de chave dedicado.
- **APIs públicas com rate limit.** As rotas JSON limitam requisições por IP (padrão 30/min) e podem exigir verificação anti-robô (Cloudflare Turnstile).
- Em produção com HTTPS, defina `SESSION_COOKIE_SECURE=true` no `.env` para que o cookie de sessão só trafegue de forma segura.

## Veja também

- [Como executar](como-executar.md)
- [Uso do painel](uso.md)
- [Hospedagem (deploy)](deploy.md)
