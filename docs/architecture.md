# Architecture and retention

The HTTP Function uses Entra Easy Auth and owner checks. Azure Durable Functions and Durable Task Scheduler run the job independently of the caller. Blob Storage holds document artifacts; Table Storage tracks job metadata. Translator handles Office translations and PDF segments; Document Intelligence extracts PDF text. The optional Foundry Responses deployment is used only when selected.

The Function's managed identity accesses private blobs, the jobs table, the scheduler, and data-plane AI roles. Translator uses its managed identity for batch file access. Local clients use `DefaultAzureCredential`. A connector uses delegated Entra access to the API, not Azure storage permissions.

Source, report, and glossary blobs are eligible for deletion 14 days after modification. Lifecycle evaluation is asynchronous and does not purge job rows, scheduler history, external notifications, or downstream SharePoint copies. Check retention of dynamically created result containers separately before use.

The result endpoint streams blobs and ZIP archives through the Azure Functions HTTP streaming extension. Blob access is bounded to the authenticated job owner, and no result is assembled in application memory.

Use the job ID to correlate operational events. Application logs should contain identifiers, counts, durations, and safe failure categories, not document text, prompts, access tokens, or request bodies. Restrict permission to reports and job files because metadata can include filenames and processing details.
