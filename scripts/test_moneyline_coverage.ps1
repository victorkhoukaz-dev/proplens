$ErrorActionPreference = 'Stop'
$outputDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) ('data/moneyline_test_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
Write-Host 'MoneyLine NFL coverage diagnostic: at most 5 read-only requests.'
Write-Host 'Checks bookmaker catalogue, Bet365, Pinnacle, Circa, then all sportsbook props.'
Write-Host 'Your key is never saved or displayed. Existing app data is unchanged.'
$secureKey = Read-Host 'Paste your MoneyLine API key' -AsSecureString
try {
    $plainKey = [System.Net.NetworkCredential]::new('', $secureKey).Password
    if ([string]::IsNullOrWhiteSpace($plainKey)) { throw 'No API key entered.' }
    $headers = @{ 'x-api-key' = $plainKey }
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    $checks = @(
        @{ Name = 'bookmakers'; Path = '/odds/bookmakers?sourceType=sportsbook' },
        @{ Name = 'bet365'; Path = '/player-props?league=nfl&sourceType=sportsbook&bookmaker=bet365&limit=50' },
        @{ Name = 'pinnacle'; Path = '/player-props?league=nfl&sourceType=sportsbook&bookmaker=pinnacle&limit=50' },
        @{ Name = 'circa'; Path = '/player-props?league=nfl&sourceType=sportsbook&bookmaker=circa&limit=50' },
        @{ Name = 'all_sportsbooks'; Path = '/player-props?league=nfl&sourceType=sportsbook&limit=50' }
    )
    foreach ($check in $checks) {
        Write-Host "`nChecking $($check.Name)..."
        try {
            $response = Invoke-WebRequest -Uri ('https://mlapi.bet/v1' + $check.Path) -Headers $headers -TimeoutSec 30 -UseBasicParsing
            [IO.File]::WriteAllText((Join-Path $outputDirectory ($check.Name + '.json')), $response.Content, [Text.UTF8Encoding]::new($false))
            $body = $response.Content | ConvertFrom-Json
            Write-Host "HTTP $($response.StatusCode); success=$($body.success); records=$(@($body.data | Where-Object { $null -ne $_ }).Count)"
            if ($check.Name -eq 'bookmakers') {
                $body.data | Select-Object bookmakerId, bookmakerName, sourceType | Format-Table -AutoSize
            } else {
                $offers = @(foreach ($event in $body.data) {
                    foreach ($player in $event.players) {
                        foreach ($market in $player.markets) {
                            foreach ($line in $market.lines) {
                                foreach ($offer in $line.offers) {
                                    [PSCustomObject]@{ Event = $event.eventId; Start = $event.startTime; Fetched = $event.fetchedAt; Player = $player.playerName; Market = $market.marketType; Line = $line.point; Book = $offer.bookmakerId; Source = $offer.sourceType; Side = $offer.selection; Price = $offer.price }
                                }
                            }
                        }
                    }
                })
                Write-Host "Actual prop offers: $($offers.Count)"
                if ($offers.Count -gt 0) {
                    $offers | Group-Object Book | Select-Object Name, Count | Format-Table -AutoSize
                    $offers | Select-Object -First 8 | Format-Table Player, Market, Line, Book, Side, Price -AutoSize
                    $offers | Export-Csv (Join-Path $outputDirectory ($check.Name + '_offers.csv')) -NoTypeInformation
                }
            }
        } catch {
            $status = $null
            if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
            Write-Host "Check failed (HTTP $status)."
            if ($status -in @(401, 403, 429) -or $null -eq $status) {
                Write-Host 'Stopping to avoid repeated authentication, rate-limit, or network failures.'
                break
            }
        }
    }
    Write-Host "`nResponses saved to: $outputDirectory"
} finally {
    $plainKey = $null
    $secureKey = $null
    $headers = $null
}
