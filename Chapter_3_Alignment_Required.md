# Align Chapter Three with the rebuilt Chapter Four

The supplied thesis copy has Chapter Four replaced. Chapters One to Three remain unchanged; the original document is preserved. Before submission, apply these method changes and replace the corresponding old diagrams:

- Section 3.9.3 and the tracking design: three calendar days (72 hours), with escalation only when elapsed time exceeds the limit. Historical durations are preserved.
- Two-party handover: named workers and password verification, not role PINs. Sender and receiver must belong to consecutive departments.
- Notifications: independent application, email and WhatsApp records. Distinguish queued, simulated, provider-accepted and verified delivery. The development evaluation did not send live messages.
- Section 3.10: scan, retrieve, validate custody/account/CT/installation, submit to the correct HES, verify a matching acknowledgement, then record connected status. Failure, timeout, pending or mismatched response means unconnected and manual HES intervention. No automatic commissioning retry.
- Replace the earlier scan-to-billing flowchart with the supplied workflow.png. Billing activation and first-reading verification are not implemented in the rebuild.
- Remove delay-classifier training, ROC-AUC, precision, recall and ridge regression from the core evaluation. This is a process model assessed through functional and integration tests.
- Use the actual evaluation populations: 100 software fixtures, 80 commissioning scenarios, 54 core checks, 11 browser checks, 11 scanner checks, 200 rendered symbols and 2 Streamlit rendering checks. These counts describe different tests and should not be combined into one accuracy denominator.
- State the data's development origin. Do not describe generated interview or questionnaire material as completed fieldwork. Retain genuine observations only where supported by your own evidence.
- Record expert consensus as incomplete until actual ratings are available. Do not retain the projected 98% financial reduction as an achieved result.

The rebuilt model does not yet independently verify GPS, installation photos, certificates, SIM provisioning or radio signal. Either implement and test those controls or remove claims that they were evaluated. The new Chapter Four makes these limits explicit.
