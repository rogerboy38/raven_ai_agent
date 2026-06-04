# L02 weight-capture clone — local staging manifest

**Staged:** 2026-06-04 by bot-iot-l01, on the L01 host, into `~/raven-bot/l02_stage/`.
**Status:** LOCAL ONLY. Nothing written to the L02 disk (`/dev/sda`); no PROD wiring; creds blank.
**Gated on:** ratification of the corrected (two-tier) architecture + answers to the 4 open questions.

## What this is
A clean, parametrized copy of L01's **submission tier** (`web_app.py` + `templates/` + the
rpi_client toolkit), ready to drop onto L02 (`/home/admin/raven-bot/`) once cleared. The
submission tier is the deployed, proven piece; the scale-automation reading tier is Phase 2.

## Included (clean)
- `rpi_client/web_app.py` — Flask submission tier (self-contained: stdlib + dotenv + flask + requests; no local imports)
- `rpi_client/templates/index.html` — operator UI
- `rpi_client/requirements.txt` — flask>=3.0, pyserial>=3.5, requests>=2.32
- `rpi_client/.env.template` — L02 params, **blank creds**, points at PROD
- `rpi_client/{scale_reader,sensor_skill_client,dummy_scale,weight_capture_client,iot_sensor_client,barcode_handler}.py` — reading-tier toolkit (NOT auto-run; Phase-2 raw material)
- `services/raven-weight.service` — L02-parametrized unit (ngrok bot2 TODO)

## Excluded (deliberately) and why
- `.env`, `.env-serversandbox` — L01 **credentials** (never copy secrets across bots)
- `weight_buffer.db` — L01's buffered weight **data** (L02 starts a fresh buffer)
- `*.bak`, `web_app_bak260418.py`, `web_app.py.bak.v12`, `index.html.bak`, `__pycache__/` — cruft
- `port_sniffer.py`, `serial_sniffer.py` — diagnostic-only dev tools

## L02 parametrization (vs L01)
| Surface | L01 | L02 (staged) |
|---|---|---|
| `ERPNEXT_URL` | sandbox.sysmayal.cloud | **erp.sysmayal2.cloud** (PROD, Phase-0 confirmed) |
| `DEVICE_ID` / `DEVICE_LABEL` | SCALE-L01 / L01 | SCALE-L02 / L02 |
| creds | set | **blank** (TODO Q4: per-bot l02 user) |
| ngrok | bot1 | bot2 (TODO Q2) |

## Compatibility note
L01 and L02 are **both Debian 13 (trixie) / python3.13** (briefing's "Bookworm" label is stale for
both — verified, not inherited). venv ports by **rebuild**, not copy.

## Deploy sequence (when cleared — applies L234: apply → enable → verify)
1. Copy `~/raven-bot/l02_stage/raven-bot/{rpi_client,services}` → L02 `/home/admin/raven-bot/`.
2. `cp rpi_client/.env.template rpi_client/.env`; fill `ERPNEXT_API_KEY/SECRET` (per-bot l02).
3. `python3 -m venv raven-env && raven-env/bin/pip install -r rpi_client/requirements.txt`.
4. Install service: copy unit, `systemctl --user`/system `enable` it (NOT just start).
5. **Verify reboot-durable**: `is-enabled` == enabled, then test-reboot and confirm it comes back.
6. Smoke test on operator-keyed path (mode:keyboard) before any serial/sensor_skill reader.

## Open questions blocking go-live
Q1 operator-keyed vs serial reader · Q2 ngrok bot2 · Q3 weight_validated payload-vs-server · Q4 per-bot l02 user
