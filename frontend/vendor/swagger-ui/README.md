# Swagger UI (vendor)

Arquivos do **Swagger UI 5.17.14** (distribuição `swagger-ui-dist`), baixados do CDN jsdelivr
(`https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/...`) para servirem self-hosted —
compatível com a CSP estrita (`script-src 'self'`) e sem dependência de CDN em produção.

| Arquivo | Origem |
|---|---|
| `swagger-ui-bundle.js` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js` |
| `swagger-ui.css` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css` |

Para atualizar: substitua os dois arquivos pela versão desejada (mesma URL, trocando a
versão) e atualize este README. O Dependabot não cobre assets JS de vendor — revise
periodicamente por CVEs do Swagger UI.
