# Schema do Banco de Dados — Portfolio de Investimentos

## Tabelas

### ativos
Cadastro de ativos (ações, criptos, CDB).

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| ticker | VARCHAR(20) | UNIQUE, NOT NULL | Código do ativo (PETR4, bitcoin, cdb_liquidez) |
| tipo | VARCHAR(10) | NOT NULL | "acao", "crypto", "cdb" |
| nome | VARCHAR(100) | | Nome descritivo |
| setor | VARCHAR(100) | NULLABLE | Setor do ativo |
| exchange | VARCHAR(20) | NULLABLE | Bolsa (BVMF, CRYPTO) |
| criado_em | DATETIME | DEFAULT now() | Data de criação |

### transacoes
Registro de compras e vendas.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| ativo_id | INTEGER | FK -> ativos.id, NOT NULL | Ativo referenciado |
| tipo_operacao | VARCHAR(10) | NOT NULL | "compra" ou "venda" |
| quantidade | FLOAT | NOT NULL | Quantidade negociada |
| preco_unitario | FLOAT | NOT NULL | Preço em BRL |
| data_operacao | DATE | NOT NULL | Data da operação |
| lock_up_ate | DATE | NULLABLE | data_operacao + 30 dias (compras) |
| observacao | VARCHAR(500) | NULLABLE | Nota opcional |
| criado_em | DATETIME | DEFAULT now() | Data de criação |

### portfolio_snapshot
Snapshots periódicos do portfólio.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| data | DATETIME | NOT NULL | Data do snapshot |
| valor_total_brl | FLOAT | NOT NULL | Valor total em BRL |
| pct_acoes | FLOAT | NULLABLE | % em ações |
| pct_crypto | FLOAT | NULLABLE | % em cripto |
| pct_cdb | FLOAT | NULLABLE | % em CDB |
| rentabilidade_total_pct | FLOAT | NULLABLE | Rentabilidade acumulada % |

### analises_ia
Histórico de análises e recomendações dos agentes IA.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| data | DATETIME | DEFAULT now() | Data da análise |
| tipo_analise | VARCHAR(30) | NOT NULL | "completa", "aporte", "realocacao_lockup" |
| agente | VARCHAR(100) | NOT NULL | Nome do agente |
| input_resumo | TEXT | | Resumo da entrada |
| output_completo | TEXT | | JSON completo do output |
| score_confianca | FLOAT | NULLABLE | 0.0 a 1.0 |
| acao_recomendada | TEXT | NULLABLE | Resumo da recomendação |
| executada | BOOLEAN | DEFAULT FALSE | Se foi executada |

### custos_tokens
Log de cada chamada à OpenAI.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| data | DATETIME | DEFAULT now() | Data da chamada |
| agente | VARCHAR(100) | NOT NULL | Nome do agente |
| modelo | VARCHAR(20) | NOT NULL | "gpt-5.2", "gpt-5.1" |
| tokens_input | INTEGER | NOT NULL | Tokens de entrada |
| tokens_output | INTEGER | NOT NULL | Tokens de saída |
| custo_usd | FLOAT | NOT NULL | Custo em dólar |
| cotacao_dolar | FLOAT | NOT NULL | PTAX no momento |
| custo_brl | FLOAT | NOT NULL | Custo em reais |
| descricao | VARCHAR(200) | NULLABLE | Descrição da chamada |

### configuracoes
Parâmetros do sistema.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| chave | VARCHAR(50) | PK | Chave da configuração |
| valor | VARCHAR(200) | NOT NULL | Valor (sempre string) |
| atualizado_em | DATETIME | DEFAULT now() | Última atualização |

### alertas
Alertas do sistema (lock-up, desvio, oportunidades).

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| tipo | VARCHAR(30) | NOT NULL | Tipo do alerta |
| mensagem | TEXT | NOT NULL | Texto em PT-BR |
| dados_json | TEXT | NULLABLE | JSON com dados extras |
| data_criacao | DATETIME | DEFAULT now() | Data de criação |
| lido | BOOLEAN | DEFAULT FALSE | Se foi lido |

### cache_precos
Cache de dados de APIs externas.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| ticker | VARCHAR(20) | NOT NULL | Ticker do ativo |
| fonte | VARCHAR(20) | NOT NULL | Fonte dos dados |
| tipo_dado | VARCHAR(20) | NOT NULL | Tipo de dado cacheado |
| dados_json | TEXT | NOT NULL | JSON serializado |
| atualizado_em | DATETIME | DEFAULT now() | Quando foi cacheado |
| expira_em | DATETIME | NOT NULL | Quando expira |

### agent_contexts
Contexto persistente dos agentes IA entre execuções.

| Coluna | Tipo | Constraints | Descrição |
|--------|------|-------------|-----------|
| id | INTEGER | PK, autoincrement | ID único |
| agent_name | VARCHAR(100) | UNIQUE, NOT NULL | Nome do agente |
| last_response_id | VARCHAR(100) | NULLABLE | ID do último response OpenAI |
| last_execution | DATETIME | NULLABLE | Última execução |
| resumo_contexto | TEXT | NULLABLE | Resumo textual |
| dados_persistentes | TEXT | NULLABLE | JSON com dados persistentes |
| execution_count | INTEGER | DEFAULT 0 | Contador de execuções |

## Valores Padrão (Seed)

| Chave | Valor | Descrição |
|-------|-------|-----------|
| alocacao_acoes | 0.50 | 50% em ações B3 |
| alocacao_crypto | 0.20 | 20% em criptoativos |
| alocacao_cdb | 0.30 | 30% em CDB liquidez diária |
| lockup_dias | 30 | Dias de lock-up após compra |
| perfil_risco | moderado | Perfil de risco do investidor |
| email_destinatario | | E-mail para relatórios |
| intervalo_atualizacao_horas | 1 | Frequência de atualização de preços |
