# 汉堡 Agent 启动脚本
Set-Location $PSScriptRoot

# 激活虚拟环境
$venvActivate = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    Write-Host "激活虚拟环境..." -ForegroundColor Cyan
    & $venvActivate
} else {
    Write-Host "未找到虚拟环境，使用系统 Python" -ForegroundColor Yellow
}

# 检查依赖
Write-Host "检查依赖..." -ForegroundColor Cyan
pip install -r requirements.txt -q

# 启动服务
Write-Host "启动服务器 http://localhost:18732 ..." -ForegroundColor Green
uvicorn server:app --host 0.0.0.0 --port 18732 --reload
