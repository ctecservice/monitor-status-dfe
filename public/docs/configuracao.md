# Configuração

Este documento cobre a configuração do Monitor Status DFe: o primeiro boot, as variáveis do arquivo `.env` e os filtros do painel `/config`.

## Primeiro boot

Antes de iniciar a aplicação pela primeira vez, copie `.env.example` para `.env` e ajuste as credenciais da API DadosJah. Depois rode o script de primeiro boot:

```
python src/scripts/configurar.py
```

Esse script (idempotente — pode rodar mais de uma vez com segurança):

1. Gera a **chave mestra** (`MONITOR_MASTER_KEY`) e a grava no `.env`, caso ainda não exista.
2. Cria o esquema do banco de dados (tabelas e valores iniciais).
3. Solicita a **senha do administrador** do painel `/config` (digitada duas vezes, sem exibir na tela) e guarda apenas o hash.

As credenciais da API **não** são alteradas por esse script: elas permanecem somente no `.env`.

## Variáveis do `.env`

O arquivo `.env.example` documenta todas as chaves. Copie-o para `.env` e ajuste os valores conforme a necessidade. Esse arquivo não deve ser versionado.

| Variável | Descrição | Padrão |
|---|---|---|
| `API_BASE_URL` | URL base da API DadosJah | `https://api-dfe.dadosjah.com.br` |
| `API_TIMEOUT_S` | Timeout (segundos) por requisição à API | `20` |
| `API_LOGIN_USUARIO` | Usuário de login da API DadosJah | *(vazio)* |
| `API_LOGIN_SENHA` | Senha de login da API DadosJah | *(vazio)* |
| `MONITOR_MASTER_KEY` | Chave mestra do monitor | *(gerada no primeiro boot)* |
| `SESSION_COOKIE_SECURE` | Restringe o cookie de sessão a HTTPS (`true`/`false`) | *(vazio = falso)* |
| `UFS` | UFs monitoradas, separadas por vírgula | todas as 27 UFs |
| `DOCUMENTOS` | Documentos monitorados, separados por vírgula | `nfe` |
| `TP_AMBS` | Ambientes: `1` = produção, `2` = homologação | `1,2` |
| `INTERVALO_COLETA_MIN` | Intervalo entre coletas, em minutos | `5` |
| `RETENCAO_DIAS` | Dias de retenção do histórico | `30` |
| `BANCO_CAMINHO` | Caminho do arquivo SQLite (relativo à raiz do projeto) | `data/statusdfe.db` |
| `LOG_NIVEL` | Nível de log: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

> **Onde colocar valores.** As credenciais da API e a chave mestra são segredos e devem ficar apenas no `.env` da instalação. Não os inclua em repositórios, imagens ou páginas públicas.

## Filtros do painel `/config`

Além do `.env`, os filtros operacionais podem ser ajustados em tempo de execução pelo painel `/config` (protegido por senha). Esses valores ficam gravados no banco de dados e são **relidos a cada ciclo de coleta**, sem necessidade de reiniciar a aplicação.

| Filtro | Padrão | Limites |
|---|---|---|
| UFs monitoradas | *(vazio = todas as UFs)* | siglas separadas por vírgula, até 200 caracteres |
| Modelos ativos | *(vazio = todos os modelos ativos)* | códigos separados por vírgula, até 200 caracteres |
| Intervalo entre coletas | 5 min | 1 a 1440 minutos |
| Timeout da API | 20 s | 1 a 120 segundos |
| Retenção de dados | 30 dias | mínimo 1 dia |
| Retenção de logs | 30 dias | mínimo 1 dia |

Observações:

- **UFs e modelos** aceitam apenas letras, vírgulas e espaços. O valor vazio significa "usar tudo".
- O **intervalo** é reaplicado ao agendador automaticamente quando alterado, sem reiniciar o processo.
- As **retenções** são aplicadas por uma tarefa diária: leituras mais antigas que o limite de dados são removidas, e arquivos de log mais antigos que o limite de logs são apagados.

## Segurança das configurações

- A senha do painel é armazenada como hash irreversível (PBKDF2), nunca em texto claro.
- Segredos reversíveis que precisem ser persistidos são cifrados com Fernet (chave derivada por PBKDF2) usando a chave mestra.
- O painel aplica proteção contra CSRF e limite de tentativas de login.
- Em produção com HTTPS, defina `SESSION_COOKIE_SECURE=true` para que o cookie de sessão só trafegue de forma segura.

## Veja também

- [Como executar](como-executar.md)
- [Uso do painel](uso.md)
- [Hospedagem (deploy)](deploy.md)
