# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

$ErrorActionPreference = "Stop"

$required = @(
    "DTS_ENDPOINT", "TASKHUB_NAME", "TRANSLATOR_ENDPOINT", "DOCINTEL_ENDPOINT",
    "STORAGE_BLOB_ENDPOINT",
    "STORAGE_QUEUE_ENDPOINT", "STORAGE_TABLE_ENDPOINT", "API_CLIENT_ID", "AZURE_TENANT_ID"
)
foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Error: $name is not set. Run azd provision and configure the required environment values."
    }
}

$values = [ordered]@{
    FUNCTIONS_WORKER_RUNTIME = "python"
    PYTHON_ENABLE_INIT_INDEXING = "1"
    AzureWebJobsStorage__blobServiceUri = $env:STORAGE_BLOB_ENDPOINT
    AzureWebJobsStorage__queueServiceUri = $env:STORAGE_QUEUE_ENDPOINT
    AzureWebJobsStorage__tableServiceUri = $env:STORAGE_TABLE_ENDPOINT
    DURABLE_TASK_SCHEDULER_CONNECTION_STRING = "Endpoint=$($env:DTS_ENDPOINT);Authentication=DefaultAzure"
}
$names = @(
    "DTS_ENDPOINT", "TASKHUB_NAME", "TRANSLATOR_ENDPOINT", "DOCINTEL_ENDPOINT",
    "TRANSLATION_MODEL_NAME", "FOUNDRY_MODEL_ENDPOINT", "STORAGE_BLOB_ENDPOINT",
    "STORAGE_QUEUE_ENDPOINT", "STORAGE_TABLE_ENDPOINT", "AZURE_LOCATION",
    "AZURE_RESOURCE_GROUP", "AZURE_FUNCTION_NAME",
    "API_BASE_URL", "API_CLIENT_ID", "AZURE_TENANT_ID", "API_IDENTITY_CLIENT_ID",
    "API_IDENTITY_PRINCIPAL_ID",
    "API_ALLOWED_AUDIENCE", "MAX_BASE64_MB", "MAX_MULTIPART_MB", "SHAREPOINT_HOSTS",
    "SLIDE_RENDER_URL", "SLIDE_RENDER_SCOPE", "SUPPORTED_LANGUAGES"
)
foreach ($name in $names) {
    $value = [Environment]::GetEnvironmentVariable($name)
    $values[$name] = if ($null -eq $value) { "" } else { $value }
}
$defaults = @{
    API_ALLOWED_AUDIENCE = $env:API_CLIENT_ID
    MAX_BASE64_MB = "10"
    MAX_MULTIPART_MB = "40"
    SUPPORTED_LANGUAGES = "en,fr,de,es,it,pt,pt-PT,nl,pl,sv,da,nb,fi"
}
foreach ($name in $defaults.Keys) {
    if ([string]::IsNullOrEmpty($values[$name])) {
        $values[$name] = $defaults[$name]
    }
}

$settings = [ordered]@{
    IsEncrypted = $false
    Values = $values
}
$json = $settings | ConvertTo-Json -Depth 10
Set-Content -Path "./src/local.settings.json" -Value $json -Encoding utf8
Write-Host "Generated src/local.settings.json using DefaultAzureCredential-compatible endpoints."
