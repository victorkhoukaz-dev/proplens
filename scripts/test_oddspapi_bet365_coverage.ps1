$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputDirectory = Join-Path $projectRoot 'data'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$baseUrl = 'https://api.oddspapi.io/v4'

Write-Host 'OddsPapi Bet365 NFL coverage test'
Write-Host 'This makes exactly two read-only API requests: the NFL market catalogue and Bet365 NFL odds.'
Write-Host 'Your key will not be saved or displayed.'
$secureKey = Read-Host 'Paste your OddsPapi API key' -AsSecureString

try {
    $plainKey = [System.Net.NetworkCredential]::new('', $secureKey).Password
    if ([string]::IsNullOrWhiteSpace($plainKey)) {
        throw 'No API key was entered.'
    }

    $catalogUrl = "$baseUrl/markets?apiKey=$plainKey&sportId=14&language=en"
    $oddsUrl = "$baseUrl/odds-by-tournaments?apiKey=$plainKey&tournamentIds=31&bookmaker=bet365&language=en&verbosity=3&oddsFormat=decimal"
    $marketCatalog = Invoke-RestMethod -Method Get -Uri $catalogUrl
    $oddsResponse = Invoke-RestMethod -Method Get -Uri $oddsUrl

    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $catalogPath = Join-Path $outputDirectory "oddspapi_nfl_market_catalog_$timestamp.json"
    $oddsPath = Join-Path $outputDirectory "oddspapi_bet365_nfl_coverage_$timestamp.json"
    [System.IO.File]::WriteAllText($catalogPath, ($marketCatalog | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($oddsPath, ($oddsResponse | ConvertTo-Json -Depth 100), [System.Text.UTF8Encoding]::new($false))

    $catalogById = @{}
    foreach ($market in @($marketCatalog)) {
        if ($null -eq $market.marketId) { continue }
        $name = "$($market.marketName) $($market.marketNameShort) $($market.marketType)".ToLowerInvariant()
        $key = $null
        if ($market.playerProp) {
            if ($name -match 'anytime touchdown|to score td|to score a touchdown') { $key = 'player_anytime_td' }
            elseif ($name -match 'passing yard|pass-yard') { $key = 'player_pass_yds' }
            elseif ($name -match 'rushing yard|rush-yard') { $key = 'player_rush_yds' }
            elseif ($name -match 'receiving yard|receiv-yard') { $key = 'player_rec_yds' }
            elseif ($name -match 'reception') { $key = 'player_receptions' }
            else { $key = 'other_player_prop' }
        }
        elseif ($name -match 'moneyline|winner') { $key = 'moneyline' }
        elseif ($name -match 'handicap|spread') { $key = 'spread' }
        elseif ($name -match 'total|over under') { $key = 'total' }
        $catalogById[[string]$market.marketId] = $key
    }

    $fixtures = @($oddsResponse)
    $coreMarkets = 0
    $playerProps = 0
    $anytimeTdMarkets = 0
    foreach ($fixture in $fixtures) {
        $markets = $fixture.bookmakerOdds.bet365.markets
        if ($null -eq $markets) { continue }
        foreach ($marketProperty in $markets.PSObject.Properties) {
            $market = $marketProperty.Value
            if ($market.marketActive -eq $false) { continue }
            switch ($catalogById[$marketProperty.Name]) {
                { $_ -in @('moneyline', 'spread', 'total') } { $coreMarkets++ }
                { $_ -eq 'player_anytime_td' } { $anytimeTdMarkets++ ; $playerProps++ }
                { $_ -match 'player_prop' } { $playerProps++ }
            }
        }
    }

    Write-Host ''
    Write-Host "Bet365 NFL fixtures returned: $($fixtures.Count)"
    Write-Host "Active core market rows (moneyline/spread/total): $coreMarkets"
    Write-Host "Active player-prop market rows: $playerProps"
    Write-Host "Active Anytime TD market rows: $anytimeTdMarkets"
    Write-Host "Raw market catalogue saved to: $catalogPath"
    Write-Host "Raw Bet365 response saved to: $oddsPath"
}
catch {
    $safeMessage = $_.Exception.Message -replace [regex]::Escape($plainKey), '[REDACTED]'
    Write-Error "OddsPapi coverage test failed: $safeMessage"
    exit 1
}
finally {
    $plainKey = $null
    $secureKey = $null
}
