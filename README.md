# Smart Meter Programme rebuild

Prepared 11 October 2026. This package implements custody tracking and a rule-based HES commissioning process. It replaces the earlier delay-prediction model. No training is needed for this process model.

## Verified result and scope

The local evaluation passed 54 core checks: 28 tracking, 16 commissioning, 3 notification and 7 HTTP API checks. All 80 commissioning scenarios had the expected initial outcome. Sixty connected automatically in the simulator and twenty required manual HES action. All twenty manual simulator confirmations succeeded.

Correct outcome handling was 100% in these scenarios, exceeding a 90% functional acceptance target. Automatic connections across the mixed cases were 75%. Neither percentage is predictive accuracy or verified live ZETDC reliability. External HES, email and WhatsApp were not used. No cloud deployment was performed.

Additional evidence: 11 browser checks, 11 scanner checks (10 photograph lookups and one cancellation), 200 decoded Code 128/QR symbols and 2 Streamlit rendering checks. Physical phone and printed-label tests remain outstanding.

## Files

- app.py: FastAPI server and browser application entry point for Vercel.
- static/: responsive dashboard, password handovers and mobile barcode scanner.
- core.py: shared database, authentication, custody, commissioning and notification logic.
- streamlit_app.py: Streamlit commissioning console using the same core and database.
- seed.py: explicit development fixture and account setup.
- worker.py: scheduled overdue checks, interrupted-request reconciliation and notification dispatch.
- tests/evaluate.py: repeatable core evaluation in temporary databases.
- evidence/: recorded checks, screenshots and runtime versions.
- Test_Barcodes_100.pdf and Test_Register_100.csv: labels and expected demonstration outcomes.

The old labels with TEST-ISK identifiers belong to the previous application. Use these new DEMO labels with the rebuild.

## Local setup

Use Python 3.13. Open a terminal in this extracted folder.

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python seed.py

The seed command asks you to choose a password of at least 12 characters. It creates development accounts named procurement, stores, tester, depot, installer, hes_officer and manager. In this demo these accounts receive the password you chose. Real workers require separate accounts and individual passwords. Existing users and meters are never overwritten by seeding.

Run the web application:

    python -m uvicorn app:app --host 127.0.0.1 --port 8000

Open http://localhost:8000. In another terminal in the same environment, run:

    python worker.py

The worker checks once per minute even if browsers are closed. For a single diagnostic sweep use python worker.py --once. Local SQLite is adequate for a small demonstration; cloud/shared use requires PostgreSQL.

For Streamlit, first install its additional dependencies:

    pip install -r requirements-streamlit.txt


    python -m streamlit run streamlit_app.py

Both processes must use the same DATABASE_URL to share records. Without it, both use meter_demo.db relative to their working folder.

## Demonstration sequence

1. Sign in as procurement. Register a new identifier with an account, CT ratio and HES. Re-enter the releasing password and supply the stores worker's password to transfer it.
2. Continue as stores, tester and depot for the remaining handovers. A meter cannot skip a department. Wrong credentials leave custody unchanged.
3. Sign in as installer. Scan a supplied label or type its ID. Enter the account and CT shown on the label and confirm physical installation.
4. DEMO-0001 through DEMO-0060 have successful simulator acknowledgements. DEMO-0061 through DEMO-0080 exercise failures. DEMO-0081 through DEMO-0100 are not yet issued to a contractor.
5. Failed automatic requests stay unconnected. Sign in as hes_officer and use the simulator-only reference SIM-MANUAL-DEMO-0061 for that example meter. Other manual cases use the corresponding meter ID. This is a simulator verification convention, not a live HES credential.
6. Sign in as manager to inspect application/email/WhatsApp outcomes. The worker or manager check processes notification records. Simulated does not mean delivered.

For a phone, use the HTTPS deployment URL. A plain HTTP LAN address usually cannot access the camera. Allow camera permission, test front/rear device behaviour, lighting, focus, cancellation, denial and repeated scans. The photograph and manual-entry paths remain available.

## Vercel deployment

Deploy this folder as a Python FastAPI project. Vercel discovers app.py. There is no JavaScript build command. Supply DATABASE_URL for a persistent PostgreSQL database, then initialise it by running seed.py once from a trusted local environment with that same URL.

Set HES_MODE=simulator and NOTIFICATION_MODE=simulator for the demonstration. Set a long random CRON_SECRET through Vercel environment settings. vercel.json requests a once-per-minute schedule. That schedule requires a Vercel plan supporting this frequency; otherwise run worker.py on a continuously running host or use an authenticated external scheduler. Do not rely on daily cron for prompt three-day escalation.

The protected /api/cron endpoint expects Authorization: Bearer followed by CRON_SECRET. Verify the scheduler actually runs after deployment and inspect its failures. Static files are mounted at /static by FastAPI.

Official platform reference: https://vercel.com/docs/frameworks/backend/fastapi
Cron reference: https://vercel.com/docs/cron-jobs

## Streamlit deployment

Use the separate Streamlit deployment ZIP, whose requirements.txt includes the Streamlit dependencies. Upload its contents to your repository and create a Streamlit Community Cloud app with streamlit_app.py as its entry point. Configure secrets through the platform, not committed files. Set DATABASE_URL to the same PostgreSQL database as Vercel and SCANNER_URL to the deployed Vercel HTTPS URL.

Set HES_MODE and NOTIFICATION_MODE to simulator until authorised interfaces are ready. The same development accounts work in both interfaces when they share the database. Streamlit is a commissioning console; the full custody interface is in the Vercel web application.

Streamlit does not replace the background scheduler. Keep the Vercel cron or an independent worker active. The database must allow TLS connections from both deployments.

Official platform references:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

## Authorised HES gateway contract

Live mode is an adapter contract, not a completed ZETDC vendor integration. Have the utility implement or approve a HTTPS gateway before selecting HES_MODE=live. Configure HES_ISKRA_URL/TOKEN and HES_SECURE_URL/TOKEN privately.

POST /commission receives meter_id, account, ct_ratio, request_id and reference. The request also carries a bearer credential and Idempotency-Key. The gateway must enforce idempotence and map the operation to the vendor's actual commissioning API.

A successful JSON response must contain status=connected, the exact meter_id, matching hes, a nonempty receipt_id and a timezone-aware confirmed_at timestamp. Accepted, missing, mismatched and timed-out responses do not mark the meter connected.

POST /confirm-manual receives the same fields plus the officer-supplied reference. It must verify existing completion in the actual HES. It must not simply echo a typed reference or repeat automatic commissioning. No billing operation is implemented.

## Email and WhatsApp configuration

Set NOTIFICATION_MODE=live only after configuring approved recipients and credentials. Email uses SMTP_SSL with SMTP_HOST, SMTP_PORT (default 465), SMTP_USER, SMTP_PASSWORD and SMTP_FROM. Set MANAGER_EMAIL and HES_EMAIL.

WhatsApp uses Twilio with TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM and TWILIO_CONTENT_SID. Set MANAGER_WHATSAPP and HES_WHATSAPP using whatsapp: followed by the international number. The approved content template must accept variable 1 as the alert text. Ensure the recipients and template are approved for this use.

Successful submission records provider acceptance, not verified delivery. Implement and validate provider delivery/bounce callbacks before claiming actual message receipt. A worker interrupted during sending can leave a sending record needing operator reconciliation; do not blindly resend uncertain messages. The current dispatch loop is intended for low-volume prototypes and needs bounded queue workers and monitoring before large-scale use.

Official messaging references:
https://www.twilio.com/docs/whatsapp/api
https://www.twilio.com/docs/messaging/guides/track-outbound-message-status

## Reproduce and extend the evaluation

    python tests/evaluate.py

This uses isolated temporary databases and writes new evidence, so timings may differ. It does not alter your application register. The tests include negative cases; do not remove failures or change their expected outcome merely to meet a target.

Browser test source is supplied in tests/browser_tests.mjs and tests/test_scanner.mjs. Use a fresh development database served at localhost:8770, the test password Prototype-Test-2026!, and a Node environment with Playwright and installed Chrome. This password is only an automated-test fixture. The scripts must be run from the project root. Python label-decoder and Streamlit check scripts are also included.

## Remaining limitations

No physical-phone acceptance, live utility commissioning, delivery confirmation, PostgreSQL deployment, independent security review or load test has been completed. Server-side GPS, installation-photo evidence, SIM/signal checks and meter-test certification are not implemented in this rebuild. It validates the narrower core: worker role, custody, account, CT and declared installation.

Account recovery, lifecycle administration, MFA, secret rotation, backups, delivery receipts and durable high-volume workers require production work. The pinned Claude project was read but was not successfully edited because editor input could not be established reliably. CLAUDE_ALIGNMENT_REQUEST.txt records the corresponding change request; the tested local source is the deliverable.
