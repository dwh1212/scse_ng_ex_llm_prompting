$ErrorActionPreference = "Continue"
$base = "https://gh.ddlc.top/https://github.com/ollama/ollama/releases/download/v0.34.2/OllamaSetup.exe"
$tmp = Join-Path $env:TEMP "ollama_chunks"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$total = 1569993232
$n = 8
$chunk = [math]::Ceiling($total / $n)

# Reuse the already-downloaded prefix as the start of chunk 0
$prefix = Join-Path $env:TEMP "OllamaSetup.exe"
if (Test-Path $prefix) {
    $P = (Get-Item $prefix).Length
} else {
    $P = 0
}
Write-Host "prefix bytes: $P"

$ranges = @()
for ($i = 0; $i -lt $n; $i++) {
    $start = [int64]$i * $chunk
    $end = [Math]::Min($start + $chunk - 1, $total - 1)
    if ($i -eq 0) { $start = [Math]::Max($start, $P) }
    if ($start -gt $end) { continue }
    $ranges += ,@($i, $start, $end)
}

# Parallel download each range with retries
$jobs = @()
foreach ($r in $ranges) {
    $jobs += Start-Job -ArgumentList $base, $r[0], $r[1], $r[2], $tmp -ScriptBlock {
        param($u, $k, $s, $e, $dir)
        $out = Join-Path $dir ("part_{0:D2}.bin" -f $k)
        for ($try = 1; $try -le 6; $try++) {
            curl.exe -s -L -C - -o $out -r "${s}-${e}" $u --connect-timeout 10 --max-time 900 --retry 3 --retry-delay 3
            if ($LASTEXITCODE -eq 0) {
                $sz = (Get-Item $out).Length
                if ($sz -eq ($e - $s + 1)) { Write-Output "chunk $k OK ($sz bytes)"; return }
                else { Write-Output "chunk $k incomplete ($sz / $($e-$s+1)), retry $try" }
            } else {
                Write-Output "chunk $k curl exit $LASTEXITCODE, retry $try"
            }
        }
        Write-Output "chunk $k FAILED"
    }
}

Write-Host "waiting for $($jobs.Count) jobs..."
$jobs | Wait-Job | Receive-Job
$jobs | Remove-Job

# Verify all chunks
$allOk = $true
for ($i = 0; $i -lt $n; $i++) {
    $f = Join-Path $tmp ("part_{0:D2}.bin" -f $i)
    if (-not (Test-Path $f)) { Write-Host "MISSING chunk $i"; $allOk = $false }
}
Write-Host "all chunks present: $allOk"

# Concatenate prefix + chunks in order
$final = Join-Path $env:TEMP "OllamaSetup_full.exe"
if ($allOk) {
    $fs = [System.IO.File]::Create($final)
    try {
        if ($P -gt 0) {
            $pfs = [System.IO.File]::OpenRead($prefix)
            try { $pfs.CopyTo($fs) } finally { $pfs.Dispose() }
        }
        for ($i = 0; $i -lt $n; $i++) {
            $f = Join-Path $tmp ("part_{0:D2}.bin" -f $i)
            if (-not (Test-Path $f)) { continue }
            $cfs = [System.IO.File]::OpenRead($f)
            try { $cfs.CopyTo($fs) } finally { $cfs.Dispose() }
        }
    } finally {
        $fs.Dispose()
    }
    $finalSize = (Get-Item $final).Length
    Write-Host "final size: $finalSize / expected $total"
    if ($finalSize -eq $total) { Write-Host "DOWNLOAD COMPLETE" } else { Write-Host "SIZE MISMATCH" }
}
