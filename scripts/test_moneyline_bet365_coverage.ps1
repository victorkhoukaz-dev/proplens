$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $projectRoot 'data'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'

# These are deliberately two separate, read-only checks:
# 1. game moneyline/spread/total markets
# 2. player props, including Anytime TD if MoneyLine supplies them
$coreUrl = 'https://mlapi.bet/v1/odds?league=nfl&sourceType=sportsbook&bookmaker=bet365&limit=50'
$propsUrl = 'https://mlapi.bet/v1/player-props?league=nfl&sourceType=sportsbook&bookmaker=bet365&limit=50'

Write-Host 'MoneyLine Bet365 NFL coverage test'
Write-Host 'This makes exactly two read-only API requests: one game-markets request and one player-props request.'
Write-Host 'Your key will not be saved or displayed.'
$secureKey = Read-Host 'Paste your MoneyLine API key' -AsSecureString

try {
    $plainKey = [System.Net.NetworkCredential]::new('', $secureKey).Password
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw 'No API key was entered.'
    }

    $headers = @{ 'x-api-key' = $plainKey }
    $coreResponse = Invoke-RestMethod -Method Get -Uri $coreUrl -Headers $headers
    $propsResponse = Invoke-RestMethod -Method Get -Uri $propsUrl -Headers $headers

    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $corePath = Join-Path $outputDirectory "moneyline_bet365_nfl_game_markets_$timestamp.json"
    $propsPath = Join-Path $outputDirectory "moneyline_bet365_nfl_player_props_$timestamp.json"
    $coreJson = $coreResponse | ConvertTo-Json -Depth 100
    $propsJson = $propsResponse | ConvertTo-Json -Depth 100
    [System.IO.File]::WriteAllText($corePath, $coreJson, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($propsPath, $propsJson, [System.Text.UTF8Encoding]::new($false))

    $coreCount = @($coreResponse.data).Count
    $propsCount = @($propsResponse.data).Count
    $coreHasBet365 = $coreJson -match '(?i)bet365'
    $propsHasBet365 = $propsJson -match '(?i)bet365'
    $propsHasAnytimeTd = $propsJson -match '(?i)player_anytime_td|anytime.*touchdown|touchdown.*anytime'

    Write-Host ''
    Write-Host "Game markets: success=$($coreResponse.success); events=$coreCount; Bet365 present=$coreHasBet365"
    Write-Host "Player props: success=$($propsResponse.success); events=$propsCount; Bet365 present=$propsHasBet365; Anytime TD present=$propsHasAnytimeTd"
    Write-Host "Game-market raw response saved to: $corePath"
    Write-Host "Player-props raw response saved to: $propsPath"
}
catch {
    Write-Error "MoneyLine coverage test failed: $($_.Exception.Message)"
    exit 1
}
finally {
    $plainKey = $null
    $secureKey = $null
}
