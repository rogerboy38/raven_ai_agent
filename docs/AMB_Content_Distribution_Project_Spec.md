# AMB Content Distribution System
## AI Agent Architecture v1.0

---

## RESUMEN EJECUTIVO

### Objetivo del Proyecto
Automatizar la distribucion de ~2000 landing pages de contenido R&D de Acemannan/Aloe Vera desde ERPNext Blog Content hacia multiples plataformas:
- WordPress (acemannan-acetypol.com)
- LinkedIn (cuenta corporativa AMB)
- Reddit (subreddits relevantes)

### Infraestructura Actual
- **ERPNext**: v2.sysmayal.cloud/desk/blog-content (15+ posts activos)
- **WordPress**: acemannan-acetypol.com (wp-admin configurado)
- **n8n**: Workflows de automatizacion existentes
- **Integracion previa**: Botones en ERPNext que publican a WordPress via n8n

### Alcance
- 1800 paginas en proceso + 200 adicionales
- Publicacion automatica con adaptacion de contenido por plataforma
- Tracking de estado de publicacion en ERPNext

---

## ARQUITECTURA DE AGENTES

### ORQUESTADOR PRINCIPAL (Master Agent)

**Nombre**: `AMB_Content_Orchestrator`

**Responsabilidades**:
1. Monitorear cola de contenido pendiente en ERPNext
2. Coordinar secuencia de publicacion entre plataformas
3. Manejar reintentos y errores
4. Reportar metricas de publicacion
5. Respetar rate limits de cada plataforma

**Prompt del Orquestador**:
```
Eres el orquestador principal del sistema de distribucion de contenido AMB.
Tu rol es coordinar la publicacion de contenido desde ERPNext hacia WordPress, LinkedIn y Reddit.

REGLAS:
1. Procesa maximo 10 posts por hora para evitar rate limits
2. Secuencia: WordPress primero, luego LinkedIn, finalmente Reddit
3. Espera confirmacion de cada fase antes de continuar
4. Si una plataforma falla, continua con las otras y marca para reintento
5. Actualiza el estado en ERPNext despues de cada publicacion exitosa

ESTADOS VALIDOS:
- pending: Esperando publicacion
- wp_published: Publicado en WordPress
- li_published: Publicado en LinkedIn  
- rd_published: Publicado en Reddit
- completed: Todas las plataformas
- error: Requiere revision manual
```

---

## FASE 1: EXTRACCION DE CONTENIDO (ERPNext Reader Agent)

### Especificacion Tecnica

**Nombre del Agente**: `ERPNext_Content_Reader`

**Objetivo**: Extraer contenido del doctype Blog Content de ERPNext

**Endpoints/Metodos**:
- API REST: `GET /api/resource/Blog Content?filters=[["status","=","pending"]]`
- Frappe Client: `frappe.get_list("Blog Content", filters={...})`

**Campos a Extraer**:
- `name`: ID del documento (BLOG-00001)
- `title`: Titulo del post
- `content`: Contenido HTML
- `topic`: Categoria/tema
- `schema_markup`: SEO schema (si existe)

**Prompt del Agente**:
```
Eres el agente de extraccion de contenido ERPNext.
Tu trabajo es obtener posts pendientes de publicacion del Blog Content.

PASOS:
1. Conecta a ERPNext via API usando las credenciales proporcionadas
2. Obtiene lista de posts con status='pending' o sin status de publicacion
3. Para cada post, extrae: title, content, topic, schema_markup
4. Limpia el HTML y prepara el contenido para cada plataforma
5. Retorna array de objetos con contenido listo para publicar

OUTPUT FORMAT:
{
  "posts": [
    {
      "id": "BLOG-00001",
      "title": "...",
      "content_html": "...",
      "content_text": "...",
      "topic": "...",
      "hashtags": ["#acemannan", "#aloevera", "..."]
    }
  ],
  "total": 15,
  "batch_id": "batch_20250127_001"
}
```

**Script para bench console (verificacion)**:
```python
# Ejecutar en bench console para verificar estructura
import frappe

# Obtener posts pendientes
posts = frappe.get_all(
    "Blog Content",
    filters={},
    fields=["name", "title", "content", "topic", "creation"],
    order_by="creation desc",
    limit=20
)

for p in posts:
    print(f"{p.name}: {p.title[:50]}...")

# Ver estructura de un post especifico
doc = frappe.get_doc("Blog Content", "BLOG-00015")
print(doc.as_dict())
```

### Formulario de Verificacion Fase 1

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T1.1 | Conexion API ERPNext exitosa | [ ] Pass / [ ] Fail | |
| T1.2 | Lista de posts obtenida correctamente | [ ] Pass / [ ] Fail | |
| T1.3 | Contenido HTML extraido sin errores | [ ] Pass / [ ] Fail | |
| T1.4 | Conversion a texto plano funcional | [ ] Pass / [ ] Fail | |
| T1.5 | Hashtags generados automaticamente | [ ] Pass / [ ] Fail | |

---

## FASE 2: PUBLICACION WORDPRESS (WordPress Publisher Agent)

### Especificacion Tecnica

**Nombre del Agente**: `WordPress_Publisher`

**Objetivo**: Publicar contenido en acemannan-acetypol.com via REST API

**Configuracion**:
- URL Base: `https://acemannan-acetypol.com/wp-json/wp/v2/`
- Autenticacion: Application Password o JWT
- Endpoint: `POST /posts`

**Mapeo de Campos ERPNext -> WordPress**:
```json
{
  "title": "blog_content.title",
  "content": "blog_content.content",
  "status": "publish",
  "categories": "[mapear desde topic]",
  "tags": "[extraer de hashtags]",
  "meta": {
    "_yoast_wpseo_metadesc": "blog_content.meta_description",
    "erpnext_id": "blog_content.name"
  }
}
```

**Prompt del Agente**:
```
Eres el agente de publicacion WordPress para AMB.
Tu trabajo es publicar posts en acemannan-acetypol.com.

PASOS:
1. Recibe contenido procesado del Content Reader
2. Formatea el HTML para WordPress (limpia estilos inline)
3. Mapea categorias del topic de ERPNext a categorias WP
4. Genera meta description si no existe
5. Publica via REST API
6. Retorna URL del post publicado y post_id

MANEJO DE ERRORES:
- 401: Token expirado - solicitar renovacion
- 429: Rate limit - esperar 60 segundos
- 500: Error servidor - reintentar 3 veces

OUTPUT:
{
  "success": true,
  "erpnext_id": "BLOG-00015",
  "wp_post_id": 1234,
  "wp_url": "https://acemannan-acetypol.com/acemannan-veterinary/",
  "published_at": "2025-01-27T10:30:00Z"
}
```

**Script n8n Workflow** (referencia existente):
```javascript
// Nodo HTTP Request para WordPress
{
  "method": "POST",
  "url": "https://acemannan-acetypol.com/wp-json/wp/v2/posts",
  "authentication": "predefinedCredentialType",
  "nodeCredentialType": "wordpressApi",
  "body": {
    "title": "{{ $json.title }}",
    "content": "{{ $json.content }}",
    "status": "publish"
  }
}
```

### Formulario de Verificacion Fase 2

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T2.1 | Autenticacion WordPress exitosa | [ ] Pass / [ ] Fail | |
| T2.2 | Post creado en estado draft | [ ] Pass / [ ] Fail | |
| T2.3 | Post publicado correctamente | [ ] Pass / [ ] Fail | |
| T2.4 | Categorias mapeadas correctamente | [ ] Pass / [ ] Fail | |
| T2.5 | Meta SEO aplicado | [ ] Pass / [ ] Fail | |
| T2.6 | URL del post accesible | [ ] Pass / [ ] Fail | |

---

## FASE 3: PUBLICACION LINKEDIN (LinkedIn Publisher Agent)

### Especificacion Tecnica

**Nombre del Agente**: `LinkedIn_Publisher`

**Objetivo**: Publicar contenido adaptado en LinkedIn (Company Page o Personal)

**Configuracion API**:
- OAuth 2.0 con scopes: `w_member_social`, `r_liteprofile`
- Endpoint: `POST https://api.linkedin.com/v2/ugcPosts`
- Rate Limit: 100 posts/dia

**Adaptacion de Contenido**:
```
Original (HTML largo) -> LinkedIn (max 3000 caracteres)
- Extraer primer parrafo como hook
- Resumir puntos clave en bullets
- Agregar CTA con link a WordPress
- Incluir hashtags relevantes (max 5)
```

**Prompt del Agente**:
```
Eres el agente de publicacion LinkedIn para AMB Wellness.
Tu trabajo es adaptar y publicar contenido cientifico de Acemannan para profesionales.

REGLAS DE ADAPTACION:
1. Maximo 3000 caracteres
2. Tono profesional/cientifico pero accesible
3. Primer parrafo debe ser un hook que capture atencion
4. Incluir 3-5 puntos clave como bullets
5. CTA: "Lee el articulo completo: [link WordPress]"
6. Hashtags: #Acemannan #AloeVera #RnD #Nutraceuticals #HealthScience

FORMATO OUTPUT:
{
  "success": true,
  "erpnext_id": "BLOG-00015",
  "linkedin_post_urn": "urn:li:share:123456789",
  "linkedin_url": "https://www.linkedin.com/feed/update/...",
  "character_count": 2847,
  "published_at": "2025-01-27T11:00:00Z"
}

EJEMPLO DE ADAPTACION:
Original: "Acemannan, the bioactive polysaccharide from Aloe vera, has gained recognition..."
LinkedIn:
"Did you know Acemannan from Aloe vera is revolutionizing veterinary medicine?

Key findings from our R&D:
* Supports immune function in cats and dogs
* Accelerates wound healing
* Anti-inflammatory properties for skin conditions

Read the full research: [link]

#Acemannan #VeterinaryMedicine #AloeVera"
```

### Formulario de Verificacion Fase 3

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T3.1 | OAuth LinkedIn conectado | [ ] Pass / [ ] Fail | |
| T3.2 | Contenido adaptado a 3000 chars | [ ] Pass / [ ] Fail | |
| T3.3 | Post publicado exitosamente | [ ] Pass / [ ] Fail | |
| T3.4 | Link a WordPress incluido | [ ] Pass / [ ] Fail | |
| T3.5 | Hashtags aplicados correctamente | [ ] Pass / [ ] Fail | |

---

## FASE 4: PUBLICACION REDDIT (Reddit Publisher Agent)

### Especificacion Tecnica

**Nombre del Agente**: `Reddit_Publisher`

**Objetivo**: Publicar contenido adaptado en subreddits relevantes

**Configuracion API**:
- Reddit API via PRAW (Python) o snoowrap (Node.js)
- OAuth 2.0 con script app credentials
- Rate Limit: ~10 posts/hora, 100/dia

**Subreddits Objetivo**:
```
- r/AloeVera (5k members)
- r/Nutraceuticals (si existe)
- r/VeterinaryMedicine (para posts veterinarios)
- r/supplements (1.2M members - requiere karma)
- r/nutrition (2.8M members)
- r/science (30M - solo papers peer-reviewed)
```

**Adaptacion de Contenido**:
```
Original (HTML largo) -> Reddit (texto markdown)
- Titulo llamativo pero no clickbait
- TL;DR al inicio
- Formato markdown con headers
- Link a fuente original
- Flair apropiado segun subreddit
```

**Prompt del Agente**:
```
Eres el agente de publicacion Reddit para AMB.
Tu trabajo es compartir contenido de investigacion Acemannan en comunidades relevantes.

REGLAS CRITICAS (evitar bans):
1. NO spam - maximo 1 post por subreddit cada 24h
2. Respetar reglas de cada subreddit
3. Incluir fuentes y referencias
4. Usar flairs correctos
5. Responder a comentarios (engagement)
6. Ratio 10:1 - por cada post propio, 10 interacciones en comunidad

FORMATO POST:
**Titulo**: [Research] Acemannan: Beneficios comprobados en salud veterinaria

**Contenido**:
TL;DR: [resumen en 2 lineas]

## Hallazgos principales
- Punto 1
- Punto 2

## Metodologia
[breve descripcion]

**Fuente**: [link a WordPress]

---
*Este contenido es parte de nuestra investigacion en AMB Wellness*

OUTPUT:
{
  "success": true,
  "erpnext_id": "BLOG-00015",
  "reddit_submissions": [
    {
      "subreddit": "r/AloeVera",
      "post_id": "abc123",
      "url": "https://reddit.com/r/AloeVera/comments/abc123",
      "flair": "Research"
    }
  ],
  "published_at": "2025-01-27T12:00:00Z"
}
```

### Formulario de Verificacion Fase 4

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T4.1 | OAuth Reddit conectado | [ ] Pass / [ ] Fail | |
| T4.2 | Post creado en subreddit test | [ ] Pass / [ ] Fail | |
| T4.3 | Markdown renderizado correctamente | [ ] Pass / [ ] Fail | |
| T4.4 | Flair aplicado | [ ] Pass / [ ] Fail | |
| T4.5 | Rate limits respetados | [ ] Pass / [ ] Fail | |

---

## FASE 5: ACTUALIZACION ESTADO ERPNext (Status Updater Agent)

### Especificacion Tecnica

**Nombre del Agente**: `ERPNext_Status_Updater`

**Objetivo**: Actualizar estado de publicacion en Blog Content despues de cada fase

**Campos a Actualizar en Blog Content**:
```python
# Agregar estos campos al doctype Blog Content
{
    "wp_published": 0,  # Check
    "wp_url": "",       # Data
    "wp_post_id": "",   # Data
    "li_published": 0,  # Check  
    "li_post_urn": "",  # Data
    "rd_published": 0,  # Check
    "rd_post_ids": "",  # Small Text (JSON)
    "distribution_status": "pending",  # Select: pending/partial/completed/error
    "last_distribution_attempt": None,  # Datetime
    "distribution_errors": ""  # Text (log de errores)
}
```

**Script bench console para agregar campos**:
```python
import frappe

# Verificar campos existentes
meta = frappe.get_meta("Blog Content")
print([f.fieldname for f in meta.fields])

# Agregar campo distribution_status si no existe
if not meta.has_field("distribution_status"):
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    custom_fields = {
        "Blog Content": [
            {
                "fieldname": "distribution_status",
                "label": "Distribution Status",
                "fieldtype": "Select",
                "options": "pending\nwp_only\nli_only\nrd_only\ncompleted\nerror",
                "insert_after": "status"
            },
            {
                "fieldname": "wp_published",
                "label": "WordPress Published",
                "fieldtype": "Check",
                "insert_after": "distribution_status"
            },
            {
                "fieldname": "wp_url",
                "label": "WordPress URL",
                "fieldtype": "Data",
                "insert_after": "wp_published"
            },
            {
                "fieldname": "li_published",
                "label": "LinkedIn Published",
                "fieldtype": "Check",
                "insert_after": "wp_url"
            },
            {
                "fieldname": "rd_published",
                "label": "Reddit Published",
                "fieldtype": "Check",
                "insert_after": "li_published"
            }
        ]
    }
    create_custom_fields(custom_fields)
    frappe.db.commit()
    print("Campos creados exitosamente")
```

**Prompt del Agente**:
```
Eres el agente de actualizacion de estado ERPNext.
Tu trabajo es mantener sincronizado el estado de publicacion en Blog Content.

DESPUES DE CADA PUBLICACION:
1. Recibe confirmacion del agente publicador
2. Actualiza campos correspondientes en ERPNext
3. Calcula distribution_status basado en publicaciones exitosas
4. Registra errores si los hay

LOGICA DE ESTADOS:
- pending: Ninguna plataforma publicada
- wp_only: Solo WordPress
- li_only: Solo LinkedIn (raro)
- partial: 2 de 3 plataformas
- completed: Las 3 plataformas exitosas
- error: Algun fallo que requiere revision
```

### Formulario de Verificacion Fase 5

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T5.1 | Campos custom creados en Blog Content | [ ] Pass / [ ] Fail | |
| T5.2 | wp_published actualizado correctamente | [ ] Pass / [ ] Fail | |
| T5.3 | li_published actualizado correctamente | [ ] Pass / [ ] Fail | |
| T5.4 | rd_published actualizado correctamente | [ ] Pass / [ ] Fail | |
| T5.5 | distribution_status calculado bien | [ ] Pass / [ ] Fail | |

---

## FASE 6: MONITOREO Y REPORTES (Analytics Agent)

### Especificacion Tecnica

**Nombre del Agente**: `Distribution_Analytics`

**Objetivo**: Generar reportes de distribucion y metricas de engagement

**Metricas a Trackear**:
```
WordPress:
- Posts publicados
- Views (via WP Stats/Jetpack)
- Time on page

LinkedIn:
- Posts publicados
- Impressions
- Likes/Comments/Shares
- Click-through rate

Reddit:
- Posts publicados
- Upvotes/Downvotes
- Comments
- Subreddit performance
```

**Reporte en ERPNext**:
```python
# Script para crear Report Builder en ERPNext
# Ejecutar en bench console

import frappe

# Query para reporte de distribucion
report_query = """
SELECT 
    name as blog_id,
    title,
    distribution_status,
    wp_published,
    li_published,
    rd_published,
    creation,
    modified
FROM `tabBlog Content`
ORDER BY creation DESC
"""

results = frappe.db.sql(report_query, as_dict=True)

# Estadisticas
total = len(results)
wp_count = sum(1 for r in results if r.get('wp_published'))
li_count = sum(1 for r in results if r.get('li_published'))
rd_count = sum(1 for r in results if r.get('rd_published'))
completed = sum(1 for r in results if r.get('distribution_status') == 'completed')

print(f"""
=== REPORTE DE DISTRIBUCION ===
Total Posts: {total}
WordPress: {wp_count} ({wp_count/total*100:.1f}%)
LinkedIn: {li_count} ({li_count/total*100:.1f}%)
Reddit: {rd_count} ({rd_count/total*100:.1f}%)
Completados (3/3): {completed} ({completed/total*100:.1f}%)
""")
```

**Prompt del Agente**:
```
Eres el agente de analytics y reportes del sistema AMB.
Tu trabajo es generar reportes de distribucion y engagement.

REPORTES A GENERAR:
1. Reporte diario: Posts distribuidos en ultimas 24h
2. Reporte semanal: Engagement por plataforma
3. Reporte mensual: ROI de contenido (views/clicks)

ALERTAS:
- Posts pendientes > 100: Alerta de backlog
- Errores > 10 en 1 hora: Alerta de sistema
- Rate limit alcanzado: Notificar pausa

FORMATO REPORTE DIARIO:
{
  "date": "2025-01-27",
  "summary": {
    "total_processed": 45,
    "wordpress": {"published": 45, "errors": 0},
    "linkedin": {"published": 43, "errors": 2},
    "reddit": {"published": 40, "errors": 5}
  },
  "pending_queue": 1755,
  "estimated_completion": "2025-02-15"
}
```

### Formulario de Verificacion Fase 6

| Test | Descripcion | Resultado | Notas |
|------|-------------|-----------|-------|
| T6.1 | Reporte diario generado | [ ] Pass / [ ] Fail | |
| T6.2 | Metricas WordPress correctas | [ ] Pass / [ ] Fail | |
| T6.3 | Metricas LinkedIn correctas | [ ] Pass / [ ] Fail | |
| T6.4 | Metricas Reddit correctas | [ ] Pass / [ ] Fail | |
| T6.5 | Alertas funcionando | [ ] Pass / [ ] Fail | |

---

## IMPLEMENTACION n8n

### Workflow Principal

```
[Webhook Trigger] --> [ERPNext Reader] --> [Content Processor]
                                                    |
                                          +---------+---------+
                                          |         |         |
                                       [WP]     [LinkedIn]  [Reddit]
                                          |         |         |
                                          +---------+---------+
                                                    |
                                          [Status Updater] --> [Analytics]
```

### Nodos Principales

1. **Schedule Trigger**: Cada 6 minutos (10 posts/hora)
2. **ERPNext Node**: GET posts pendientes
3. **AI Agent Node**: Adaptar contenido por plataforma
4. **HTTP Request**: Publicar a cada plataforma
5. **ERPNext Node**: Actualizar estado
6. **Error Handler**: Manejar fallos y reintentos

---

## CRONOGRAMA DE IMPLEMENTACION

| Fase | Duracion | Dependencias | Entregable |
|------|----------|--------------|------------|
| Fase 1 | 2 dias | Acceso API ERPNext | Reader Agent funcional |
| Fase 2 | 3 dias | Fase 1, WP credentials | WordPress Publisher |
| Fase 3 | 4 dias | Fase 1, LinkedIn OAuth | LinkedIn Publisher |
| Fase 4 | 3 dias | Fase 1, Reddit App | Reddit Publisher |
| Fase 5 | 2 dias | Fases 2-4 | Status Updater |
| Fase 6 | 2 dias | Fase 5 | Analytics Dashboard |

**Total estimado**: 16 dias laborales

---

## CHECKLIST FINAL DE PROYECTO

| Item | Estado | Responsable |
|------|--------|-------------|
| API Keys configuradas (WP, LI, RD) | [ ] | DevOps |
| Campos custom en Blog Content | [ ] | Frappe Dev |
| Workflow n8n creado | [ ] | n8n Admin |
| Tests unitarios pasando | [ ] | QA |
| Documentacion actualizada | [ ] | Tech Writer |
| Monitoreo Sentry/Logs | [ ] | DevOps |
| Backup pre-lanzamiento | [ ] | SysAdmin |

---

## NOTAS ADICIONALES

### Consideraciones de Rate Limits

| Plataforma | Limite | Estrategia |
|------------|--------|------------|
| WordPress | Sin limite practico | Batch de 50/hora |
| LinkedIn | 100 posts/dia | 4 posts/hora |
| Reddit | 10 posts/hora/subreddit | Rotacion de subreddits |

### Estimacion de Tiempo Total

Con 2000 posts y procesando ~50/dia:
- **Tiempo estimado**: 40 dias laborales
- **Recomendacion**: Paralelizar publicaciones WP (mas rapido) y secuenciar LI/RD

---

*Documento generado: 2025-01-27*
*Version: 1.0*
*Autor: AMB Technical Team*