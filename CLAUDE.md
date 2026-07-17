# CLAUDE.md — Memória Principal do Projeto CNES Combo

> Leia este arquivo antes de qualquer mudança relevante no projeto.
> Nome do painel: **CNES Combo**. Projeto irmão: **Painel Credenciamento** (`gaiafranklinalexandre-blip/Credenciamentos`) — mesma arquitetura, reaproveitada aqui.
> Fonte do painel: **Inter** (não Raleway — trocada por legibilidade a pedido do usuário).
> **Push automático autorizado**: usuário pediu para não perguntar antes de dar `git push origin main` neste repositório — commitar e enviar direto após mudanças em `index.html`/`sync_combo.py`/`CLAUDE.md` (o Render faz deploy automático). Continua valendo pedir confirmação para operações destrutivas (force-push, reset, etc.).

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
  ↓ MySQL — tabela combo_equipamentos (upsert por cnes + co_equipamento + co_tipo_equipamento + competencia, nunca trunca)
index.html (a construir) ← fetch API em tempo real
```

### Decisão de arquitetura crítica: formato longo, não largo

O CSV de origem chega em formato **largo**: cada exportação mensal adiciona um novo par de colunas `QT_YYYYMM`/`ATIVO_YYYYMM`. Espelhar isso 1:1 no MySQL exigiria `ALTER TABLE` manual todo mês.

Em vez disso, `sync_combo.py`:
1. Detecta dinamicamente (via regex) todos os pares `QT_*/ATIVO_*` presentes no cabeçalho do CSV recebido — sem precisar de mudança de código quando um mês novo aparece.
2. Transforma (melt) cada linha larga em N linhas longas: uma por `(cnes, equipamento, competência)`.
3. Envia para `sync-combo.php?action=sync_combo`, que faz **upsert** (`INSERT ... ON DUPLICATE KEY UPDATE`) na chave única `(cnes, co_equipamento, co_tipo_equipamento, competencia)` — nunca faz `TRUNCATE`, então competências antigas não enviadas no arquivo do mês corrente são preservadas.

> ⚠️ **Bug histórico corrigido em 2026-07-17**: a chave única viveu por um tempo como só `(cnes, co_equipamento, competencia)`, sem `co_tipo_equipamento`. Como `co_equipamento` sozinho **se repete** entre equipamentos diferentes (ex: código `03` é tanto BALANÇA ANTROPOMÉTRICA quanto FOTÓFORO CLÍNICO), o upsert tratava dois equipamentos distintos como o mesmo registro e um sobrescrevia o outro — sumindo 4 dos 16 equipamentos do combo da base. Se essa classe de bug reaparecer (equipamentos faltando em `?action=filtros`), suspeitar primeiro de joins/chaves usando `co_equipamento` sem `co_tipo_equipamento` junto.

Isso também cobre os dois cenários possíveis de exportação mensal (arquivo trazendo só a competência nova, ou trazendo o histórico completo) sem precisar de lógica condicional — o upsert é idempotente nos dois casos.

---

## Arquivos críticos

| Arquivo | Localização | Observação |
|---|---|---|
| `sync_combo.py` | Raiz do repo | Lê CSV, normaliza, envia para API |
| `sync-combo.php` | Hostinger (manual) | API PHP + MySQL — **gitignored**, contém credenciais reais |
| `equipamentos_combo.csv` | Raiz local | Base mensal — **gitignored**, não versionar |
| `index.html` | Raiz do repo | Frontend do painel (CNES Combo) |

---

## Estrutura de dados

### Origem (`equipamentos_combo.csv`)
`CO_CNES, NO_FANTASIA, SG_UF, NO_MUNICIPIO, DS_EQUIPAMENTO, CO_TIPO_EQUIPAMENTO, CO_EQUIPAMENTO, QT_YYYYMM, ATIVO_YYYYMM (repetido por competência)`

- 16 tipos de equipamento no combo.
- `ATIVO_*` é binário: `SIM` / `NAO`.
- Uma linha por `(CNES, equipamento)` — não por competência.

### Destino (tabela `combo_equipamentos`, MySQL)
Uma linha por `(cnes, co_equipamento, co_tipo_equipamento, competencia)`. Campos: `cnes, nome_fantasia, uf, municipio, ds_equipamento, co_tipo_equipamento, co_equipamento, competencia (DATE), quantidade, ativo`.

---

## Regra crítica de negócio: linha de base e "itens do combo"

O painel **não é um espelho da base** — ele precisa calcular quantos equipamentos foram efetivamente entregues pelo programa Combo, distinguindo do que já existia antes.

- **Linha de base:** competência `2026-01` (marco zero da entrega do combo). Definida em `sync-combo.php` como `BASELINE_COMPETENCIA = '2026-01-01'`.
- Alguns equipamentos **já existiam** em alguns estabelecimentos antes do combo (ex: câmara para conservação de imunobiológicos) — isso é esperado e **não conta** como item do combo.
- Outros equipamentos começaram **zerados** e passaram a ser cadastrados depois — esses são de fato do combo.
- **Fórmula:** `incremento_combo = GREATEST(quantidade_competencia_atual - quantidade_em_2026-01, 0)`, calculado por `(cnes, co_equipamento)`. Feito via `LEFT JOIN` da tabela `combo_equipamentos` com ela mesma (linha atual vs linha da competência baseline) — **não é armazenado**, é calculado em tempo de consulta no `sync-combo.php`. Isso evita reprocessar o histórico no Python a cada sync.
- Exemplo do usuário: 10 geladeiras em `2026-01`, 11 em `2026-02` → **1 item do combo cadastrado** naquele CNES/equipamento.
- Na própria competência baseline (`2026-01`), `incremento_combo` é sempre 0 para todos — é o marco zero, por definição.

### Métricas derivadas dessa regra
- **Itens do combo cadastrados** (volume): `SUM(incremento_combo)` — quantas unidades a mais foram registradas desde a baseline.
- **Cobertura (% de cadastro dos equipamentos)**: proporção de slots `(cnes × equipamento)` com `incremento_combo > 0` sobre o total de slots — mede quantos dos "espaços esperados" já receberam pelo menos 1 unidade do combo. Não confundir com o volume: um CNES pode ter `incremento_combo = 5` num único equipamento e isso conta como 1 slot coberto. Usada nos rankings por UF e por equipamento.
- **CNES com pelo menos 1 item do combo**: `COUNT(DISTINCT cnes)` onde algum equipamento daquele CNES tem `incremento_combo > 0` na competência.
- **Panorama (gráfico de evolução)**: série temporal de `itens_cadastrados` por competência, comparada à meta de entrega (ver regra abaixo) — mostra o crescimento do cadastro ao longo do tempo desde a baseline.

---

## Regra crítica de negócio: meta de entrega (10.000 por equipamento)

O plano de entrega do combo prevê **10.000 unidades de cada um dos equipamentos** (constante `TARGET_POR_EQUIPAMENTO` no `index.html`, hoje 16 tipos de equipamento — número lido dinamicamente de `?action=filtros`).

- **Meta nacional total** = `10.000 × número de tipos de equipamento em escopo` (1 se o filtro de equipamento estiver ativo; senão, todos os tipos existentes na base).
- A meta é **calculada só a partir do filtro de equipamento** — filtros de UF/município/CNES **não** reduzem a meta proporcionalmente, porque não há regra de distribuição geográfica do plano de entrega. Isso é intencional: ao filtrar por uma UF pequena, o "Progresso da meta" no KPI e no panorama continua comparando contra o total nacional (é avisado na tela via `secao-sub`).
- Usada em dois lugares do `index.html`:
  - KPI **"Progresso da meta de entrega"** = `itens_cadastrados / meta_total`.
  - Gráfico **Panorama**: barra de `itens_cadastrados` por competência + linha tracejada horizontal fixa na meta.
- Se o plano de entrega mudar (novo valor por equipamento, ou meta que varie por UF/tipo), ajustar `TARGET_POR_EQUIPAMENTO` e a função `metaTotal()` no `index.html` — hoje é um valor único fixo, não vem do banco.

---

## Regras principais de desenvolvimento

- Não usar frameworks JS — vanilla JS, mesmo padrão do Painel Credenciamento.
- `sync-combo.php` nunca vai para o GitHub — gitignored, sobe manualmente no Hostinger.
- Não versionar `.csv`, `.xlsx`, `.pbix`, `desktop.ini`, `~$*`.
- A API `?action=data` **exige filtro por competência** (padrão: mais recente) — o dataset normalizado passa de meio milhão de linhas, nunca devolver tudo de uma vez sem filtro.
- Para o dashboard, preferir os endpoints agregados (`?action=stats`) em vez de processar o dataset bruto no navegador — volume é muito maior que o do Credenciamento.
- Ao editar `index.html`, sempre fazer commit e push para `main`.
- Fonte do painel é **Inter** (Google Fonts) — não trocar de volta para Raleway, foi pedido explícito por legibilidade.
- Busca de município é **autocomplete** (texto livre + sugestões), não um `<select>` — a lista completa de municípios (com UF, pois o nome sozinho se repete no Brasil) é carregada uma vez em `allMunicipios` no `init()` via `?action=municipios`. Ao escolher uma sugestão, UF e município são setados juntos para evitar ambiguidade entre municípios homônimos de UFs diferentes.
- O mapa Leaflet é **por município** (não por UF) e **dinâmico**: só desenha municípios com `itens_cadastrados > 0` na competência filtrada. Posições vêm de `MUNICIPIO_COORDS`, um objeto `{"UF|NOME_SEM_ACENTO": [lat,lon]}` com ~5.078 municípios embutido diretamente no `index.html` (~190KB), casado a partir da base pública `kelvins/municipios-brasileiros` (IBGE) por nome normalizado + UF. 27 municípios da base do combo não bateram o nome (a maioria são Regiões Administrativas do DF, que não existem como município no IBGE) e por isso não aparecem no mapa — isso é esperado, não é bug. Os dados do mapa vêm de `?action=ranking&tipo=municipio&apenas_com_item=1&limit=6000`, não de `?action=stats`.
- Se a base de origem trouxer municípios novos no futuro, rodar novamente `scripts/build_municipio_coords.py` (instruções no topo do arquivo) e colar o novo `MUNICIPIO_COORDS` no `index.html` — não há atualização automática desse lookup.
- Ao selecionar um equipamento no filtro, o checkbox "Somente unidades com item cadastrado" da tabela detalhada é **auto-marcado** (`onEquipamentoChange()`), para responder diretamente "quais unidades já têm esse equipamento".
- Rankings "Top estabelecimentos" e "Top municípios" (`?action=ranking&tipo=cnes|municipio`) ordenam por `itens_cadastrados DESC` no próprio SQL — quem cadastrou mais fica no topo.
- Não existe (ainda) uma "fila de prioridade de contato" no painel — foi removida a pedido do usuário porque `incremento_combo` mede cadastro no CNES, não confirma que o equipamento foi fisicamente recebido. Só reintroduzir esse tipo de lista se houver uma fonte de dado que confirme recebimento de fato.

---

## Próximos passos

1. Subir `sync-combo.php` manualmente no Hostinger e rodar `sync_combo.py` pela primeira vez (~964 mil registros normalizados, ~322 lotes de 3.000).
2. Validar o painel em produção (`https://cnescombo.onrender.com`) com dados reais.
3. Revisar se a meta de 10.000/equipamento continua válida conforme o plano de entrega evolui (ver regra acima).
