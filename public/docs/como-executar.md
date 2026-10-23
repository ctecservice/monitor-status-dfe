# Como executar

Passo a passo para rodar o Monitor Status DFe localmente do zero, no Windows e no Linux, com solução de problemas comuns.

## Pré-requisitos

- **Python 3.12** instalado e disponível no PATH.
- Acesso à internet (para consultar a API DadosJah).
- Credenciais de login da API DadosJah (`API_LOGIN_USUARIO` e `API_LOGIN_SENHA`).

Para verificar o Python:

```
python --version
```

No Windows, o comando pode ser `py -3.12 --version`.

---

## Windows

### 1. Criar o ambiente virtual e instalar dependências

Na pasta do projeto, execute:

```
criar-venv.bat
```

Isso cria a pasta `.venv` e instala as dependências do `requirements.txt`.

### 2. Preparar as configurações

Copie os arquivos de exemplo e ajuste os valores:

```
copy .env.example .env
copy config.example.json config.json
```

Abra o `.env` e preencha ao menos `API_LOGIN_USUARIO` e `API_LOGIN_SENHA`. No `config.json` ficam as configurações operacionais (UFs, modelos, intervalo, retenções, links e a porta em `web.porta`, padrão `5628`).

### 3. Abrir o terminal com o ambiente ativado

```
entrar-venv.bat
```

### 4. Primeiro boot

```
python src/scripts/configurar.py
```

O script gera a chave mestra e cria o banco.

### 5. Iniciar o monitor

```
python src/app.py
```

Acesse `http://127.0.0.1:5628` (a porta é configurável em `config.json`, em `web.porta`).

---

## Linux

### 1. Criar o ambiente virtual e instalar dependências

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Preparar as configurações

```bash
cp .env.example .env
cp config.example.json config.json
```

Edite o `.env` e preencha `API_LOGIN_USUARIO` e `API_LOGIN_SENHA`. No `config.json` ficam as configurações operacionais (UFs, modelos, intervalo, retenções, links e a porta em `web.porta`, padrão `5628`).

### 3. Primeiro boot

```bash
python src/scripts/configurar.py
```

### 4. Iniciar o monitor

```bash
python src/app.py
```

Acesse `http://127.0.0.1:5628` (a porta é configurável em `config.json`, em `web.porta`).

---

## Verificação rápida

- Painel: `http://127.0.0.1:5628/`
- Saúde do monitor: `http://127.0.0.1:5628/health` (deve retornar `"scheduler": "ativo"`)

A primeira coleta roda após o primeiro intervalo configurado (padrão: 5 minutos) — o painel mostra "Sem coletas ainda" até lá; as seguintes seguem o mesmo intervalo.

---

## Solução de problemas

### A porta 5628 já está em uso

Sintoma: ao iniciar, aparece um erro informando que o endereço já está em uso (`Address already in use`).

Causas comuns: outra instância do monitor em execução ou outro programa usando a porta 5628.

Verifique e encerre o processo que ocupa a porta. No Windows:

```
netstat -ano | findstr :5628
```

Anote o PID da última coluna e encerre com `taskkill /PID <numero> /F`.

No Linux:

```bash
ss -ltnp | grep :5628
```

Encerre com `kill <numero>`. Se preferir, troque a porta em `config.json` (`web.porta`).

### O arquivo `.env` não existe

Sintoma: o monitor reclama de configuração ausente ou de credenciais da API.

Copie o exemplo e ajuste os valores: `copy .env.example .env` (Windows) ou `cp .env.example .env` (Linux). Sem `API_LOGIN_USUARIO` e `API_LOGIN_SENHA` corretos, a coleta não consegue autenticar.

### O painel mostra "sem dados" na maioria das células

"Sem dados" indica que o monitor não conseguiu obter resposta da fonte. Verifique:

- as credenciais da API no `.env`;
- a conectividade do servidor com a internet;
- o valor de `API_BASE_URL`;
- o nível de log (`LOG_NIVEL=DEBUG`) durante a investigação, para ver as mensagens de erro da coleta nos arquivos em `logs/`.

---

## Veja também

- [Configuração](configuracao.md)
- [Uso do painel](uso.md)
- [Hospedagem (deploy)](deploy.md)
