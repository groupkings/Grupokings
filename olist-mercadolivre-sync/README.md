# Olist/Tiny → Mercado Livre

Ferramenta de linha de comando que puxa **todos os produtos do Olist/Tiny**
(API v2, autenticação por token) e cria/atualiza os **anúncios no Mercado
Livre** (API oficial, OAuth2).

- ✅ Paginação automática de todos os produtos do Tiny
- ✅ Mapeamento produto Tiny → item do Mercado Livre (título, preço, estoque,
  imagens, marca, EAN, descrição sem HTML)
- ✅ Previsão automática de categoria do ML pelo título
- ✅ **Não duplica**: procura anúncio existente pelo SKU (`seller_custom_field`)
  e reusa; grava o estado em `sync_state.json` para retomar de onde parou
- ✅ Renovação automática do access token (o refresh token do ML rotaciona)
- ✅ Retentativas com backoff e respeito a rate limit (429)
- ✅ **Modo `--dry-run`** (padrão): simula tudo sem publicar nada

> ⚠️ Comece **sempre** com `--dry-run` e depois teste com `--publish --limit 5`
> antes de subir o catálogo inteiro.

## Instalação

```bash
cd olist-mercadolivre-sync
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # e preencha as credenciais
```

## Configuração (`.env`)

| Variável | Onde obter |
|---|---|
| `TINY_TOKEN` | Tiny → Configurações → **Tokens da API (API v2)** |
| `ML_CLIENT_ID` / `ML_CLIENT_SECRET` | https://developers.mercadolivre.com.br/devcenter (sua aplicação) |
| `ML_REFRESH_TOKEN` | gerado no fluxo OAuth do ML (troca do `code` de autorização) |

Demais opções (tipo de anúncio, garantia, quantidade padrão, timeouts) têm
valores padrão e estão comentadas no `.env.example`.

### Como obter o Refresh Token do Mercado Livre (resumo)

1. No DevCenter, crie a aplicação e configure a **Redirect URI**.
2. Autorize acessando:
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_APP_ID&redirect_uri=SUA_REDIRECT`
3. O ML redireciona com `?code=XXXX`. Troque o code por tokens:
   ```bash
   curl -X POST https://api.mercadolibre.com/oauth/token \
     -d grant_type=authorization_code -d client_id=SEU_APP_ID \
     -d client_secret=SEU_SECRET -d code=XXXX -d redirect_uri=SUA_REDIRECT
   ```
4. Guarde o `refresh_token` retornado no `.env`.

## Uso

```bash
# 1) Simular (não publica nada) — recomendado primeiro
python main.py --dry-run

# 2) Testar publicando poucos produtos de verdade
python main.py --publish --limit 5

# 3) Publicar TODOS os produtos ativos
python main.py --publish

# Só produtos inativos / todos
python main.py --dry-run --situacao I
python main.py --dry-run --situacao ""

# Renovar/imprimir o access token do ML
python main.py --refresh-token
```

## Testes

```bash
python tests/test_mapper.py     # ou: pytest tests/
```

## Como funciona

```
Tiny API v2                 mapper                 Mercado Livre API
-----------                 ------                 -----------------
produtos.pesquisa.php  ─┐
                        ├─► produto Tiny ─► payload item ─► POST /items
produto.obter.php      ─┘                     │             (ou PUT se já existe)
(descrição, imagens,                          └─► previsão de categoria
 dimensões, EAN)                                  (domain_discovery)
```

O estado de cada SKU (criado/atualizado/erro + `item_id`) é salvo em
`sync_state.json`. Rodar novamente **pula os já concluídos** e retenta os que
falharam.

## Limitações / próximos passos

- A **previsão de categoria** usa o `domain_discovery` do ML a partir do
  título. Categorias muito específicas podem exigir ajuste manual — nesses
  casos o item é registrado como `no_category` no estado para revisão.
- **Atributos obrigatórios** variam por categoria. O mapeador envia os
  básicos (marca, modelo, GTIN); se uma categoria exigir atributos adicionais,
  o ML retorna o erro e o SKU fica marcado como `failed` com a mensagem —
  basta complementar o `mapper.py` para aquela categoria.
- Frete/dimensões e variações (grade de cor/tamanho) não são enviados nesta
  versão; podem ser adicionados em `mapper.build_ml_payload`.
