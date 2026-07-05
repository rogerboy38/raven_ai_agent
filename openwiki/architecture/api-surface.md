# Architecture: `api/` surface (classification)

40+ modules. Classification at commit `b268ff1c`:

**Live pipeline**: `agent.py`, `channel_utils.py`, `agent_prompts.py`, `context_builder.py`, `response_formatter.py`, `cache_layer.py`, `memory_manager.py`.

**Live feature endpoints** (whitelisted, called by UI/webhooks/scheduler): `sales_order_upload.py`, `sales_invoice_upload.py`, `po_extractor.py`, `multimodal_ingest.py`, `smart_delivery.py`, `smart_invoice.py`, `banxico_fx.py`, `weight_api.py`, `alexa_to_raven.py`, `openai_webhook.py`, `raven_webhook_handler.py`, `sales_order_webhook.py`, `batch_sync.py`, `bom_fixer.py`/`bom_helpers.py`, `document_reports.py`, `enhanced_search.py`, `consolidation_agent.py`/`consolidation_scheduler.py`, `queue_handlers.py`, `truth_hierarchy.py`, `tds_resolver.py`, `workflows.py`.

**Built but unwired (V2 constellation)**: `agent_v2.py`, `agent_supervisor.py`, `multi_agent_router.py`, `intent_resolver.py`, `raven_v2_functions.py`.

**Dead / snapshots — delete**: `agent_V1.py`, `router.py`, `router.py.bak_bug28`, `workflows.py.bak_bug24`, `command_router.py`, `perf_test.py`.

When adding an endpoint, put domain logic in `agents/` or `skills/` and keep `api/` modules thin (whitelisting + serialization only).
