# CLAUDE.md — Memória Principal do Projeto Painel Combo

> Leia este arquivo antes de qualquer mudança relevante no projeto.
> Projeto irmão: **Painel Credenciamento** (`gaiafranklinalexandre-blip/Credenciamentos`) — mesma arquitetura, reaproveitada aqui.

---

## Objetivo do painel

Painel web de monitoramento do **Combo de Equipamentos da APS** — kit de equipamentos médicos (balança, dermatoscópio, desfibrilador, doppler vascular, eletrocardiógrafo, oxímetro, etc.) distribuído aos estabelecimentos de saúde (CNES). Monitora, mês a mês, quantidade e status de ativação de cada equipamento por estabelecimento.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | HTML + CSS + JavaScript (vanilla, sem framework) |
| Fonte de dados | API PHP (Hostinger) → MySQL (mesmo banco do Painel Credenciamento, tabela própria) |
| Sincronização | Python (`sync_combo.py`) + csv + requests |
| Versionamento | Git → GitHub (`gaiafranklinalexandre-blip/CNESCombo`) |
| Deploy | Render — `https://cnescombo.onrender.com` (service ID `srv-d99crpt7vvec73fduk00`), auto-deploy no push para `main` |

---

## Arquitetura atual

```
equipamentos_combo.csv (exportado mensalmente, formato largo: colunas QT_YYYYMM/ATIVO_YYYYMM crescem todo mês)
  ↓ sync_combo.py (Python) — detecta colunas de competência automaticamente e normaliza (melt) para formato longo
API PHP (sync-combo.php — Hostinger, NÃO está no GitHub)
  ↓ MySQL — tabela combo_equipamentos (upsert por cnes + co_equipamento + competencia, nunca trunca)
index.html (a construir) ← fetch API em tempo real
```

### Decisão de arquitetura crítica: formato longo, não largo

O CSV de origem chega em formato **largo**: cada exportação mensal adiciona um novo par de colunas `QT_YYYYMM`/`ATIVO_YYYYMM`. Espelhar isso 1:1 no MySQL exigiria `ALTER TABLE` manual todo mês.

Em vez disso, `sync_combo.py`:
1. Detecta dinamicamente (via regex) todos os pares `QT_*/ATIVO_*` presentes no cabeçalho do CSV recebido — sem precisar de mudança de código quando um mês novo aparece.
2. Transforma (melt) cada linha larga em N linhas longas: uma por `(cnes, equipamento, competência)`.
3. Envia para `sync-combo.php?action=sync_combo`, que faz **upsert** (`INSERT ... ON DUPLICATE KEY UPDATE`) na chave única `(cnes, co_equipamento, competencia)` — nunca faz `TRUNCATE`, então competências antigas não enviadas no arquivo do mês corrente são preservadas.

Isso também cobre os dois cenários possíveis de exportação mensal (arquivo trazendo só a competência nova, ou trazendo o histórico completo) sem precisar de lógica condicional — o upsert é idempotente nos dois casos.

---

## Arquivos críticos

| Arquivo | Localização | Observação |
|---|---|---|
| `sync_combo.py` | Raiz do repo | Lê CSV, normaliza, envia para API |
| `sync-combo.php` | Hostinger (manual) | API PHP + MySQL — **gitignored**, contém credenciais reais |
| `equipamentos_combo.csv` | Raiz local | Base mensal — **gitignored**, não versionar |
| `index.html` | Raiz do repo (a criar) | Frontend do painel |

---

## Estrutura de dados

### Origem (`equipamentos_combo.csv`)
`CO_CNES, NO_FANTASIA, SG_UF, NO_MUNICIPIO, DS_EQUIPAMENTO, CO_TIPO_EQUIPAMENTO, CO_EQUIPAMENTO, QT_YYYYMM, ATIVO_YYYYMM (repetido por competência)`

- 16 tipos de equipamento no combo.
- `ATIVO_*` é binário: `SIM` / `NAO`.
- Uma linha por `(CNES, equipamento)` — não por competência.

### Destino (tabela `combo_equipamentos`, MySQL)
Uma linha por `(cnes, co_equipamento, competencia)`. Campos: `cnes, nome_fantasia, uf, municipio, ds_equipamento, co_tipo_equipamento, co_equipamento, competencia (DATE), quantidade, ativo`.

---

## Regras principais de desenvolvimento

- Não usar frameworks JS — vanilla JS, mesmo padrão do Painel Credenciamento.
- `sync-combo.php` nunca vai para o GitHub — gitignored, sobe manualmente no Hostinger.
- Não versionar `.csv`, `.xlsx`, `.pbix`, `desktop.ini`, `~$*`.
- A API `?action=data` **exige filtro por competência** (padrão: mais recente) — o dataset normalizado passa de meio milhão de linhas, nunca devolver tudo de uma vez sem filtro.
- Para o dashboard, preferir os endpoints agregados (`?action=stats`) em vez de processar o dataset bruto no navegador — volume é muito maior que o do Credenciamento.
- Ao editar `index.html`, sempre fazer commit e push para `main`.

---

## Próximos passos

1. Desenhar o frontend (`index.html`): KPIs, filtros (UF/município/competência/equipamento), tabela por estabelecimento, indicador de % combo completo por CNES.
2. Definir regra de negócio de "combo completo" (ex: todos os 16 equipamentos com `ativo = SIM` na competência).
3. Subir `sync-combo.php` manualmente no Hostinger e rodar `sync_combo.py` pela primeira vez.
