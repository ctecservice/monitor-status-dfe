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
│   Rotas de página          Rotas de API JSON                 │
│   (/, /uf/<uf>, /config)   (/api/status, /api/uf/.../...)    │
│                          │                                   │
│                          ▼                                   │
│   ┌───────────────────────────────────────────────────┐     │
│   │              Camada de serviços                    │     │
│   │   cliente da API DadosJah · classificação          │     │
│   └───────────────┬───────────────────────┬───────────┘     │
│                   │                       │                  │
│      ┌────────────▼────────┐   ┌──────────▼──────────┐      │
│      │   Jobs agendados     │   │  Utilitários         │      │
│      │  coleta · retenção   │   │ config · banco · log │      │
│      └────────────┬─────────┘   │ segredos             │      │
│                   │             └──────────────────────┘      │
└───────────────────┼─────────────────────────────────────────┘
                    │ HTTP (Bearer token)
                    ▼
          ┌───────────────────────┐
          │   API DadosJah         │
          │  (status das SEFAZ)    │
          └───────────┬───────────┘
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
| `app.py` | Aplicação Flask: rotas de página, rotas de API JSON, endpoint de saúde e painel de configuração. Inicia o agendador e o banco ao subir. |
| `jobs/` | Tarefas agendadas: `coletar` (ciclo periódico de consulta às SEFAZ) e `reter` (limpeza diária de dados e logs). |
| `services/` | Regras de negócio: cliente HTTP da API DadosJah, autenticação e classificação do código de status em estado do semáforo. |
| `utils/` | Utilitários transversais: leitura de configuração, conexão e esquema do banco, logging e criptografia de segredos. |
| `web/` | Interface: templates Jinja2 (`templates/`), estilos, JavaScript e logos (`static/`). |

## Modelo de dados

O banco é um único arquivo SQLite em modo WAL, com quatro tabelas:

| Tabela | Conteúdo |
|---|---|
| `leituras` | Histórico de status por UF × documento × ambiente (código, motivo, latência, versão, data/hora, erro). |
| `modelos_dfe` | Modelos de DF-e suportados (extensível por dados; seed inicial `nfe`). |
| `configuracoes` | Filtros operacionais da instância (UFs, modelos, intervalo, timeout, retenções). |
| `segredos` | Credenciais e valores sensíveis armazenados de forma criptografada. |

O índice `idx_leituras_lookup` (UF, documento, ambiente, data de coleta) acelera a busca pela última leitura de cada combinação.

## Ciclo de vida de uma leitura

1. **Agendamento** — o agendador dispara o ciclo de coleta conforme o intervalo configurado.
2. **Autenticação** — o serviço de autenticação faz login na API DadosJah e obtém um token de acesso, mantido em memória e renovado quando necessário.
3. **Consulta** — para cada combinação de modelo × UF × ambiente, o cliente HTTP consulta o endpoint de status correspondente, medindo o tempo de resposta.
4. **Classificação** — o código de status devolvido é traduzido em um estado do semáforo; falhas de coleta resultam em "sem dados".
5. **Gravação** — a leitura é gravada na tabela `leituras` com data/hora e os campos técnicos da resposta.
6. **Exibição** — o painel lê a leitura mais recente de cada combinação e a série histórica, montando a grade e o detalhe por UF.
7. **Retenção** — uma tarefa diária remove leituras e logs mais antigos que os limites configurados.

## Decisões técnicas

- **Flask** — framework web leve, suficiente para as páginas e APIs do monitor, com baixo consumo de recursos.
- **SQLite em modo WAL** — banco em arquivo único, sem servidor dedicado; o modo WAL permite leituras concorrentes com uma escrita sem bloquear o painel.
- **APScheduler** — agendamento em processo, permitindo coletas periódicas e uma tarefa diária de retenção sem depender de `cron` externo.
- **httpx** — cliente HTTP com suporte a timeouts e medição de tempo de resposta.
- **Criptografia (Fernet + PBKDF2)** — segredos reversíveis são cifrados com Fernet, com chave derivada por PBKDF2 a partir da chave mestra; senhas de administrador usam hash irreversível (PBKDF2) em vez de criptografia reversível.

## Veja também

- [API JSON](api.md)
- [Hospedagem (deploy)](deploy.md)
