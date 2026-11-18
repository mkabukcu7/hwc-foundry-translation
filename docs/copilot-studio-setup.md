# Copilot Studio setup

This is a manual integration. Durable Functions runs the job; Copilot Studio starts it and retrieves results.

1. Register a single-tenant API in Entra, set its Application ID URI to `api://<API_CLIENT_ID>`, and expose delegated scope `Translation.Invoke`. Configure Function Easy Auth to require authentication from that tenant and accept the API audience.
2. Register the connector client, add its generated redirect URL, and grant the delegated API permission with the required consent. Set the connector to OAuth 2.0 with the tenant-specific v2 authorization and token endpoints. Request `api://<API_CLIENT_ID>/Translation.Invoke`. Store connector credentials in the connector configuration, not this repo.
3. Define connector operations against `https://<function-app-host>/api`. Use the same caller connection for submit, status, and download; the API binds the job to the Entra user, not the optional `userId` field.

## Submit and poll

`POST /jobs` with `Content-Type: application/json`:

```json
{
  "fileName": "campaign_brief_en.docx",
  "contentBase64": "<base64-encoded-document>",
  "sourceLanguage": "en",
  "targetLanguages": ["fr", "de"],
  "glossaryName": "sample"
}
```

`202 Accepted`:

```json
{
  "jobId": "<job-id>",
  "statusUrl": "https://<function-app-host>/api/jobs/<job-id>"
}
```

`400 Bad Request` for an unsupported code:

```json
{
  "error": "Language 'ja' is not enabled in phase 1. Enabled: en,fr,de,es,it,pt,pt-PT,nl,pl,sv,da,nb,fi."
}
```

In the agent flow, accept one file and a list of target codes. Submit once, poll `GET /jobs/<job-id>` for at most 60 seconds, and return terminal status or the job ID for follow-up. For `complete`, download `GET /jobs/<job-id>/result?lang=<code>` for each reported output. With the SharePoint connector, save each file under `/<campaign>/<lang>/`. Post the links and status to Teams or Outlook after writes complete. Use bounded retries for SharePoint throttling. Report failures without sending raw service responses or document contents to the notification channel.
