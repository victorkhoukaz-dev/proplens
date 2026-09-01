$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $projectRoot 'data'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outputPath = Join-Path $outputDirectory "moneyline_all_nfl_player_props_$timestamp.json"
$requestUri = 'https://mlapi.bet/v1/player-props?league=nfl&sourceType=sportsbook&limit=50'

Write-Host 'MoneyLine all NFL sportsbook player-props test'
Write-Host 'This makes exactly one API request. Your key will not be saved or displayed.'
$secureKey = Read-Host 'Paste your MoneyLine API key' -AsSecureString

try {
    $plainKey = [System.Net.NetworkCredential]::new('', $secureKey).Password
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw 'No API key was entered.'
    }

    $response = Invoke-RestMethod -Method Get -Uri $requestUri -Headers @{ 'x-api-key' = $plainKey }
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

    $responseJson = $response | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($outputPath, $responseJson, [System.Text.UTF8Encoding]::new($false))

    $eventCount = @($response.data).Count
    $hasDrakeMaye = $responseJson -match 'Drake Maye'
    $hasBet365 = $responseJson -match 'bet365'
    $hasPinnacle = $responseJson -match 'pinnacle'

    Write-Host ''
    Write-Host "Request succeeded: $($response.success)"
    Write-Host "NFL events returned: $eventCount"
    Write-Host "Drake Maye found: $hasDrakeMaye"
    Write-Host "Bet365 found: $hasBet365"
    Write-Host "Pinnacle found: $hasPinnacle"
    Write-Host "Raw response saved to: $outputPath"
}
catch {
    Write-Error "MoneyLine test failed: $($_.Exception.Message)"
    exit 1
}
finally {
    $plainKey = $null
    $secureKey = $null
}
