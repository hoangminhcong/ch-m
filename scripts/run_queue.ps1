# Hàng đợi sinh luật cho MỘT key (lần chạy chính thức, runbook C9). Không thuộc dấu code (chỉ .py được băm).
# Chạy lần lượt từng cấu hình; cấu hình còn ERROR (VD hết hạn mức ngày) → chờ rồi chạy lại ĐÚNG lệnh đó (chỉ khoản
# còn lỗi) cho tới khi 0 ERROR mới sang cấu hình sau. Chạy lại script bất kỳ lúc nào: cấu hình đã xong được bỏ qua.
#
#   .\scripts\run_queue.ps1 -KeyVar CEREBRAS_API_KEY -Jobs "Y-noL12","Y@results\cap_official_rep2"
#   Mỗi job: "<cấu hình>" (thư mục mặc định results\cap_official) hoặc "<cấu hình>@<thư mục>".
param(
    [Parameter(Mandatory = $true)][string]$KeyVar,
    [Parameter(Mandatory = $true)][string[]]$Jobs,
    [int]$WaitMinutes = 30,
    [int]$MaxAttempts = 60
)
$ErrorActionPreference = "Stop"
$Python = "C:\Users\hayab\.venvs\nsai-compliance\Scripts\python.exe"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONIOENCODING = "utf-8"

function Get-ErrorCount([string]$OutDir, [string]$Config) {
    # -1 = chưa có file hoặc chưa đủ 218 khoản; còn lại = số khoản ERROR
    $file = Join-Path $OutDir "predictions_$Config.json"
    if (-not (Test-Path $file)) { return -1 }
    $code = "import json,sys; p=json.load(open(sys.argv[1],encoding='utf-8'))['predictions']; " +
            "print(-1 if len(p) < 218 else sum(1 for v in p.values() if v['outcome']=='ERROR'))"
    return [int](& $Python -c $code $file)
}

foreach ($job in $Jobs) {
    $parts = $job.Split("@", 2)
    $config = $parts[0]
    $outDir = if ($parts.Count -gt 1) { $parts[1] } else { "results\cap_official" }
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    $log = Join-Path $outDir "run_$config.log"
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        if ((Get-ErrorCount $outDir $config) -eq 0) { break }
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Write-Host "`n=== $stamp  $config -> $outDir  (lần $attempt, key $KeyVar)" -ForegroundColor Cyan
        "`n=== $stamp  $config -> $outDir  (lần $attempt)" | Out-File -Append -Encoding utf8 $log
        & $Python scripts\run_cap_generation.py --provider cerebras --config $config --key-var $KeyVar `
            --min-interval 30 --max-tokens 8000 --out-dir $outDir 2>&1 | Tee-Object -Append -FilePath $log
        $left = Get-ErrorCount $outDir $config
        if ($left -eq 0) { break }
        Write-Host "Còn $left khoản ERROR (-1 = chưa đủ 218 khoản) — chờ $WaitMinutes phút rồi chạy lại" -ForegroundColor Yellow
        Start-Sleep -Seconds ($WaitMinutes * 60)
    }
    if ((Get-ErrorCount $outDir $config) -ne 0) {
        Write-Host "DỪNG: $config vẫn chưa xong sau $MaxAttempts lần — xem $log" -ForegroundColor Red
        exit 1
    }
    Write-Host "XONG $config ($outDir): 218/218, 0 ERROR" -ForegroundColor Green
}
Write-Host "`nHàng đợi của $KeyVar đã xong hết." -ForegroundColor Green
